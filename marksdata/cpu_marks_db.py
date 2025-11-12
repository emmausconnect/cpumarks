"""Code for maintaining the (important) CSV file in which CPU marks are searched"""
import os
import sys
import csv
import time
import datetime
import argparse
import enum
import logging
import json
import re
from http import HTTPStatus
from typing import Any, Union, Optional

import urllib3
import requests

_datestamp = time.strftime("%Y%m%d.%H%M%S", datetime.datetime.now().timetuple())
_onLinux = sys.platform.startswith('linux')

_THEPAGE = 'https://www.cpubenchmark.net/CPU_mega_page.html'

# Setting test mode
_IMAX = 0  # value for production version
# _IMAX = 30  # for testing

_logger = logging.getLogger("get_cpu_marks_db")
_logger.level = logging.WARNING
_hdlr = logging.StreamHandler()
_formatter = logging.Formatter('[%(levelname)-7s] %(filename)s(%(lineno)d): %(message)s')
_hdlr.setFormatter(_formatter)
_logger.addHandler(_hdlr)


def _to_intstr_when_possible(s: Any) -> Union[str, Any]:
    if not isinstance(s, str):
        return s
    try:
        i = int(s.replace(',', ''))
    except ValueError:
        return s
    return str(i)


@enum.unique
class Source(enum.Enum):
    """Encodes where we are reading the data from: the web or an HTML file"""
    WEB = enum.auto()
    HTML = enum.auto()


@enum.unique
class Technique(enum.Enum):
    """Encodes how we get and analyze the input (we have two different techniques)"""
    UI = enum.auto()
    SCRAP = enum.auto()


class CpuMarks:
    """Main class"""
    _d: list = []  # [dict[str, str]] = []
    _keys_to_keep = {
        'CPU Mark': 'cpumark',
        'CPU Name': 'name',
        'Category': 'cat',
        'Cores': 'cores',
        'Socket': 'socket',
        'TDP (W)': 'tdp',
        'Thread Mark': 'thread',
    }
    _ordered_fields = ['name', 'cores', 'cpumark', 'thread', 'tdp', 'socket', 'cat']

    @classmethod
    def _init(cls, tech: Technique) -> None:
        cls._get_the_data_from_web(tech=tech)

    def __init__(self, tech: Technique = Technique.SCRAP) -> None:
        if not CpuMarks._d:
            CpuMarks._d = []
            self._init(tech)

    @classmethod
    def get_number_of_cpus(cls) -> int:
        """Returns the number of know CPUs at the time"""
        return len(cls._d)

    @classmethod
    def get_cpu_list(cls):  # -> list[dict[str, str]]:
        """Returns all the data in a single JSON-style list"""
        return cls._d

    @classmethod
    def get_field_list(cls):  # -> list[str]:
        """Returns the ordered field list for the resulting CSV file"""
        return cls._ordered_fields

    @classmethod
    def _get_the_data_from_web(cls, tech: Technique) -> None:
        """Collects the primary data from the web"""
        if tech == Technique.SCRAP:
            cls._get_the_data_from_web_scrap()
        else:
            # cowardly give up
            _logger.fatal("Don't know this technique to get the data from the web")

    @classmethod
    def _get_the_data_from_json_file(cls, json_file: str) -> None:
        """Load data from a pre-fetched JSON file"""
        _logger.info(f"Loading data from JSON file: {json_file}")
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                d = json.load(f)
            
            if not d:
                _logger.error("No data found in JSON file")
                return
            
            _logger.info(f"Loaded {len(d)} CPU records from JSON")
            cls._process_cpu_data(d)
            
        except FileNotFoundError:
            _logger.error(f"JSON file not found: {json_file}")
        except json.JSONDecodeError as exc:
            _logger.error(f"Failed to parse JSON file: {exc}")
            
    @classmethod
    def _get_the_data_from_web_scrap(cls) -> None:
        """Collects the primary data from the web by accessing one magic page via PHP bridge"""
        
        # Priority 1: Check if pre-fetched JSON file exists (for OVH mutualized hosting)
        prefetch_json = os.getenv('CPU_MARKS_PREFETCH_JSON', 'cpumarks-prefetch.json')
        if os.path.isfile(prefetch_json):
            _logger.info(f"Using pre-fetched JSON file: {prefetch_json}")
            cls._get_the_data_from_json_file(prefetch_json)
            return
        
        # Priority 2: Original direct method (fallback for non-restricted environments)
        cls._get_the_data_direct()
    
    @classmethod
    def _get_the_data_direct(cls) -> None:
        """Collects the primary data from the web by accessing one magic page"""
        agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Safari/605.1.15'
        
        # Complete browser-like headers
        initial_headers = {
            'User-Agent': agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
        }
        
        sessid = ''

        # Step 1: Get PHPSESSID from initial request
        _logger.info(f"Fetching PHPSESSID from {_THEPAGE}")
        try:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            session = requests.Session()
            # Set session-wide SSL verification
            session.verify = False
            
            response = session.get(
                _THEPAGE,
                headers=initial_headers,
                timeout=15,
                allow_redirects=True
            )
            
            if response.status_code != 200:
                _logger.error(f"Initial request failed with status {response.status_code}")
                return
            
            # Extract PHPSESSID from cookies
            if 'PHPSESSID' in session.cookies:
                sessid = session.cookies['PHPSESSID']
                _logger.info(f"Found PHPSESSID: {sessid}")
            else:
                # Try to extract from Set-Cookie header
                for cookie in response.cookies:
                    if cookie.name == 'PHPSESSID':
                        sessid = cookie.value
                        _logger.info(f"Extracted PHPSESSID from cookies: {sessid}")
                        break
                
                if not sessid:
                    _logger.error("Could not extract PHPSESSID from the response")
                    _logger.debug(f"Response headers: {response.headers}")
                    _logger.debug(f"Response cookies: {response.cookies}")
                    return
                
        except requests.exceptions.Timeout:
            _logger.error("Request for PHPSESSID timed out")
            return
        except requests.exceptions.RequestException as exc:
            _logger.error(f"Request for PHPSESSID failed: {exc}")
            return

        # Step 2: Fetch the actual data using the session ID
        ajax_headers = {
            'User-Agent': agent,
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': _THEPAGE,
            'X-Requested-With': 'XMLHttpRequest',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
        }
        
        ts = int(time.time() * 1000)
        url = f"https://www.cpubenchmark.net/data/?_={ts}"
        
        _logger.info(f"Fetching data from {url}")
        
        try:
            # Wait a bit to simulate human behavior
            time.sleep(0.5)
            
            r = session.get(url, headers=ajax_headers, timeout=30)
            s = HTTPStatus(r.status_code)

            if s != HTTPStatus.OK:
                _logger.fatal(f'Request for the marks failed with status "{s.value}: {s.description}"')
                _logger.debug(f"Response text: {r.text[:500]}")
                return

            d = json.loads(r.content.decode())['data']
            cls._process_cpu_data(d)

            lnames = [_['name'] for _ in cls._d]
            if len(lnames) != len(set(lnames)):
                duplicates = {x: lnames.count(x) for x in lnames if lnames.count(x) > 1}
                _logger.warning(f'Found {len(duplicates)} duplicate names')
                for _ in duplicates:
                    _logger.warning(f'{_}: {duplicates[_]} occurrences')
                    
        except requests.exceptions.Timeout:
            _logger.error("Request for data timed out")
            return
        except requests.exceptions.RequestException as exc:
            _logger.error(f"Request for data failed: {exc}")
            return
        except (json.JSONDecodeError, KeyError) as exc:
            _logger.error(f"Failed to parse JSON response: {exc}")
            _logger.debug(f"Response text: {r.text[:500]}")
            return
    
    @classmethod
    def _process_cpu_data(cls, d: list) -> None:
        """Process the raw CPU data from the API"""
        cls._d = []
        for el in d:
            # In most cases, "cpuCount" is represented as 1: int in the JSON structure; however, when
            # there are more than 1 CPU, "cpuCount" is represented as a string, e.g., "2"
            # Since we don't keep track of cpuCount, we need to update the value of "cores"
            try:
                cpucount = int(el['cpuCount'])  # == 1 most of the time
                cores = int(el['cores'])
                if cpucount > 1:
                    el['cores'] = str(cores * cpucount)
                    if cpucount == 2:
                        el['name'] = '[Dual CPU] ' + el['name']
                    elif cpucount == 3:
                        el['name'] = '[3-Way CPU] ' + el['name']
                    elif cpucount == 4:
                        el['name'] = '[Quad CPU] ' + el['name']
                    elif cpucount == 5:
                        el['name'] = '[5-Way CPU] ' + el['name']
                    elif cpucount == 8:
                        el['name'] = '[8-Way CPU] ' + el['name']
                    elif cpucount == 12:
                        el['name'] = '[12-Way CPU] ' + el['name']
                    elif cpucount == 16:
                        el['name'] = '[16-Way CPU] ' + el['name']
                else:
                    el['cores'] = str(cores + int(el['secondaryCores']))
            except Exception as exc:  # pylint: disable=W0718
                _logger.warning(f'Exception {exc}) was raised while processing {el}')
            # Filter out the unused keys; keep values as they are
            toapp = {k: _to_intstr_when_possible(v).strip() for k, v in el.items() if
                     k in cls._keys_to_keep.values()}
            toapp['cannonname'] = re.sub(r'^\[[^\[]+]\s*', '', el['name']).strip()
            if toapp['cannonname'] != el['name']:
                pass
            cls._d.append(toapp)


def write_csvfile(data: list, csvfile: str, fieldlist: list = None) -> None:
    """Saves a list of records into a CSV file"""
    if fieldlist:
        f = set(data[0].keys())
        if not set(fieldlist).issubset(f):
            _logger.error('Some fields are missing')
        fieldnames = fieldlist + sorted(list(f - set(fieldlist)))
    else:
        fieldnames = sorted(data[0].keys())
    with open(csvfile, mode='w', newline='\n', encoding='utf-8') as cfile:
        writer = csv.DictWriter(cfile, fieldnames=fieldnames, delimiter=';', lineterminator='\n')
        writer.writeheader()
        i = 0
        for row in data:
            i += 1
            if _IMAX and i > _IMAX:
                break
            try:
                writer.writerow(row)
            except UnicodeEncodeError as e:
                print(f'Got UnicodeEncodeError at row {i} ({e})')
                print(row)
            else:
                _logger.debug(row)


if __name__ == "__main__":

    class MyFormatter(argparse.MetavarTypeHelpFormatter, argparse.RawTextHelpFormatter):
        """Special formatter of mine"""
        pass


    epilog_ = fr"""


====== Utilisation ======

Le but de ce script est de récupérer les données d'évaluation des CPUs depuis la page
{_THEPAGE} et de les stocker dans un fichier CSV.

===== Exemples =====

  python ...{os.sep}get_cpu_marks_db.py
    ==> prend les données sur le web et crée le fichier cpumarks-<date>.csv

  python ...{os.sep}get_cpu_marks_db.py -o monfichier.csv
    ==> prend les données sur le web et crée le fichier monfichier.csv

  Note: "..." désigne le chemin vers le répertoire où est installé le script
 
"""

    parser_ = argparse.ArgumentParser(description=f'Extraire les données de {_THEPAGE} vers fichier CSV',
                                      epilog=epilog_, add_help=False, formatter_class=MyFormatter)

    parser_.add_argument('-h', '--help', action='help', help="Afficher ce message et quitter")

    parser_.add_argument('--output-file', type=str, required=False, metavar="CSVFILE",
                         help="Nom du fichier CSV à produire [cpumarks-<date>.csv]")

    parser_.add_argument("-f", "--force", default=False, action='store_true',
                         help="Forcer la ré-écriture du fichier CSV"
                         "\nPar défaut, si le fichier existe déjà, le script le signale et s'arrête")

    parser_.add_argument("-v", "--verbose", default=False, action='store_true',
                         help="Activer le mode verbeux")

    parser_.add_argument("--debug", default=False, action='store_true',
                         help="(expert) Activer le mode mise au point (très verbeux...)")

    args_ = parser_.parse_args()
    if args_.verbose:
        _logger.setLevel(logging.INFO)

    if args_.debug:
        _logger.setLevel(logging.DEBUG)

    for i_ in sorted(vars(args_).items()):
        _logger.info(f'{i_[0]:<12}: {i_[1]}')

    ofile_ = ""
    if not args_.output_file:
        ofile_ = f'cpumarks-{_datestamp}.csv'
    else:
        ofile_ = os.path.realpath(args_.output_file)
        if os.path.isfile(ofile_):
            if not args_.force:
                parser_.exit(13, f'Output file {ofile_} exists; use -f|--force to overwrite it\n')
            if not os.access(ofile_, os.W_OK):
                parser_.exit(14, f'{ofile_} is not writeable\n')
        odir_ = os.path.dirname(ofile_)
        if not os.path.isdir(odir_):
            parser_.exit(15, f'Output directory {odir_} does not exist\n')
        if os.path.isdir(odir_) and not os.access(odir_, os.W_OK):
            parser_.exit(16, f'Cannot create output file in {odir_} (directory write-protected)\n')

    # THIS IS WHERE get_the_data_from_web IS CALLED:
    # When you instantiate CpuMarks(), it calls __init__
    # __init__ checks if _d is empty and calls _init(tech)
    # _init calls _get_the_data_from_web(tech)
    # _get_the_data_from_web calls _get_the_data_from_web_scrap()
    cpumarks_ = CpuMarks()
    
    print(f'Found {cpumarks_.get_number_of_cpus()} CPUs')

    d_ = cpumarks_.get_cpu_list()

    print(f'Writing CSV file {ofile_}')
    write_csvfile(d_, ofile_, fieldlist=cpumarks_.get_field_list())

    sys.exit(0)