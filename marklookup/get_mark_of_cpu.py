"""Implements the search for the mark of a given CPU"""
import re
import sys
import os
import argparse
import logging
import csv
import json
import enum
import math
from collections import defaultdict

_OURCPUNAMESANDMARKS = 'our_cpunames_and_marks.json'

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULTMARKSFILE = os.path.join(_SCRIPT_DIR, '..', 'marksdata', 'cpumarks.csv')

_logger = logging.getLogger("get_all_audits")
_logger.level = logging.WARNING
_hdlr = logging.StreamHandler()
# formatter_ = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(message)s')
_formatter = logging.Formatter('[%(levelname)-7s] %(filename)s(%(lineno)d): %(message)s')
_hdlr.setFormatter(_formatter)
_logger.addHandler(_hdlr)


class CpuAssessor:
    """Main class"""

    @enum.unique
    class MatchStep(enum.Enum):
        """Encodes the steps at which the assessment algorithm concluded"""
        FAILED = enum.auto()
        SIMPLE_0 = enum.auto()
        SIMPLE_1 = enum.auto()
        SIMPLE_2 = enum.auto()
        SIMPLE_3 = enum.auto()
        CLEVER_1 = enum.auto()
        CLEVER_2 = enum.auto()
        CLEVER_3_1 = enum.auto()
        CLEVER_3_2 = enum.auto()
        DESPERATE_1 = enum.auto()

        def __repr__(self):
            return self.name

    __is_initialized = False
    __marks: dict = {}
    __markswithsets: dict = {}
    __marksnoat: dict = {}

    @staticmethod
    def init(marksfile: str):
        """Wrapper to avoid multiple initializations"""
        if CpuAssessor.__is_initialized:
            return

        with open(marksfile, 'r') as csvfile_:
            reader_ = csv.DictReader(csvfile_, delimiter=';')
            line = 2
            for r in reader_:
                try:
                    nam = r['name']
                except KeyError:  # need to adapt to CSV files from different sources
                    try:
                        nam = r['NAME']
                    except KeyError:
                        try:
                            nam = r['CPUNAME']
                        except KeyError as exc:
                            raise RuntimeError("Unable to guess which column has the name of the CPU") from exc
                if 'Intel' in nam or 'AMD' in nam:
                    try:
                        m = r['cpumark']
                    except KeyError:  # need to adapt to CSV files from different sources
                        try:
                            m = r['CPUMARK']
                        except KeyError as exc:
                            raise RuntimeError("Unable to guess which column has the mark of the CPU") from exc
                    CpuAssessor.__marks[nam] = (int(m), line)
                line += 1

        CpuAssessor.__marksnoat = {k.split('@')[0].strip(): v for k, v in CpuAssessor.__marks.items() if '@' in k}
        CpuAssessor.__markswithsets = {k: {"toks": CpuAssessor._keytoset(k), "mark": v}
                                       for k, v in CpuAssessor.__marks.items()}

    def __init__(self, mf: str):
        CpuAssessor.init(mf)
        CpuAssessor.__is_initialized = True

    @classmethod
    def _keytoset(cls, k: str):  # -> set[str]:
        li = re.split(r'[ \-;,@]+', k)
        # re.split(r'[ \-\;\,@]+', 'AMD PRO A10-8730B R5, 10 COMPUTE CORES 4C+6G @ 3.45GHz')
        # ['AMD', 'PRO', 'A10', '8730B', 'R5', '10', 'COMPUTE', 'CORES', '4C+6G', '3.45GHz']
        s = set()
        for t in li:
            if not t or 'Duo' in t:
                continue
            m = re.match(r'^(?P<D>\d+)(?P<L>\w+)$', t)
            if re.match(r'^(?P<D>\d+)$', t) or not m:
                s.add(t)
            else:
                # m.groupdict()  # Out[16]: {'D': '8730', 'L': 'B'}
                s.add(m.groupdict()['D'])
                s = s.union(set(m.groupdict()['L']))
        return s

    @classmethod
    def _nmatch(cls, x: str):  # -> tuple[int, tuple[MatchStep, int, str], list[str]]:
        det = []
        ret = cls.__marksnoat.get(x, (0, 0))
        if ret[0]:
            return ret[0], (cls.MatchStep.SIMPLE_0, ret[1], x), det
        cx = x.replace('(R)', '')
        cx = cx.replace('(TM)', '')
        cx = cx.replace(' CPU', '')
        # cx = cx.replace(' Duo', '')
        m = re.match(r'.*(?P<keep>(Intel|AMD).*)', cx)  # remove everything before Intel|AMD
        if m:
            cx = m.groupdict()['keep']
        cx = cx.split('w/')[0].strip()
        cx = cx.split(',')[0]  # remove everything after and including a ','
        ret = cls.__marks.get(cx, (0, 0))
        if ret[0]:
            return ret[0], (cls.MatchStep.SIMPLE_1, ret[1], cx), det
        if cx.startswith('AMD'):
            cx = cx.split(' with')[0]  # remove everything after and including a "' with'"
        ret = cls.__marks.get(cx, (0, 0))
        if ret[0]:
            return ret[0], (cls.MatchStep.SIMPLE_2, ret[1], cx), det
        ret = cls.__marksnoat.get(cx, (0, 0))
        if ret[0]:
            return ret[0], (cls.MatchStep.SIMPLE_3, ret[1], cx), det
        # 'Intel Core i5-3380M' is found as 'Intel Core i5-3380M @ 2.90GHz' in cls.__marks
        # ==> we need to tamper with cls.__marks a bit...
        # Idea: try to turn entries with 'Intel...@ x.yzGHz' into two entries with same score while making sure the
        # added entry does not already exist
        # ks= [_ for _ in cls.__marks if _.startswith('Intel') and re.match(r'^(?P<keep>(Intel).*) @ ?\d\.\d\d?GHz', _)]
        # ...add code here...
        x = x.replace('(R)', '').replace('(TM)', '').replace(' CPU', '')
        mys = cls._keytoset(x)
        candidates1 = [k for k, v in cls.__markswithsets.items() if v['toks'] <= mys]
        if len(candidates1) == 1:
            ret = cls.__marks.get(candidates1[0], (0, 0))
            return ret[0], (cls.MatchStep.CLEVER_1, ret[1], candidates1[0]), det
        threshold2 = 3 if 'AMD' in x else 4
        candidates2 = [k for k, v in cls.__markswithsets.items() if len(mys & v['toks']) >= threshold2]
        if len(candidates2) == 1:
            ret = cls.__marks.get(candidates2[0], (0, 0))
            return ret[0], (cls.MatchStep.CLEVER_2, ret[1], candidates2[0]), det
        candidates3 = [_ for _ in candidates2 if cls._keytoset(_) > mys]
        if len(candidates3) == 1:
            ret = cls.__marks.get(candidates3[0], (0, 0))
            return ret[0], (cls.MatchStep.CLEVER_3_1, ret[1], candidates3[0]), det
        for c in candidates3:
            cs = cls._keytoset(c.split('@')[0].strip())
            if cs == mys:
                ret = cls.__marks.get(c, (0, 0))
                return ret[0], (cls.MatchStep.CLEVER_3_2, ret[1], c), det
        # Very special cases:
        # ['Pentium T4500', 'Intel Core2 T7200', 'Pentium E5400', 'Intel Pentium Dual T3200']
        # m = re.match(r'.*(?P<model>[A-Z]\d{1,4}).*', x)
        m = re.match(r'.*(?P<model>[A-Z]\d{1,4}).*', x)
        if m:
            model = m.groupdict()['model']
            candidates4 = [k for k, v in cls.__markswithsets.items() if model in v['toks']]
            if len(candidates4) == 1:
                ret = cls.__marks.get(candidates4[0], (0, 0))
                return ret[0], (cls.MatchStep.DESPERATE_1, ret[1], candidates4[0]), det
        else:
            candidates4 = []

        det += [f'"{x}" ==> {mys}', f'{candidates1}', f'{candidates2}', f'{candidates3}', f'{candidates4}']
        return 0, (cls.MatchStep.FAILED, 0, ''), det

    @classmethod
    def assess(cls, cpu: str):  # -> tuple[int, tuple[MatchStep, int, str], list[str]]:
        """Most important entry point!"""
        if not cls.__is_initialized:
            raise RuntimeError("Class CpuAssessor must be initialized before use")
        return cls._nmatch(cpu)

    @classmethod
    def test(cls, lmfile: str, threshold: float = 3.0):  # -> tuple[dict[str, int], list[tuple[str, list[tuple[int, str]]]]]:
        """Like name suggests it, for use by maintainers"""
        _logger.info('Running massive test')
        with open(lmfile, 'r') as jfile:
            ournames = json.load(jfile)

        nhit = nmiss = ncorrect = nfalse = 0
        missed: list = []  # [tuple[str, list[tuple[int, str]]]] = []
        stats: dict = {_.name: 0 for _ in cls.MatchStep}
        failures = []
        weird_: int = 0
        for nam, ourmarks in ournames.items():
            ma, (meth, nline, line), det = cls._nmatch(nam)
            if meth not in [cls.MatchStep.SIMPLE_0, cls.MatchStep.SIMPLE_1]:
                _logger.debug(f'"{nam}" has a mark of {ma} ({meth}, {nline}, "{line}")')
            stats[meth.name] += 1
            if meth == cls.MatchStep.FAILED:
                failures.append(nam)
                print(det)
            if ma:
                nhit += 1
                lmarks_ = [float(_[0]) for _ in ourmarks]
                avg_ = int(sum(lmarks_) / len(ourmarks))
                min_ = int(min(lmarks_))
                max_ = int(max(lmarks_))
                deltapcmin_ = abs((100.0 * (int(ma) - min_)) / min_)
                deltapcmax_ = abs((100.0 * (int(ma) - max_)) / max_)
                deltapcavg_ = abs((100.0 * (int(ma) - avg_)) / avg_)
                sq_diffs_ = [(x - avg_) ** 2 for x in lmarks_]
                variance_ = sum(sq_diffs_) / len(lmarks_)
                sd_ = math.sqrt(variance_)
                if deltapcavg_ <= threshold and not (deltapcmin_ <= threshold and deltapcmax_ <= threshold):
                    weird_ += 1
                if deltapcavg_ <= threshold:
                    ncorrect += 1
                else:
                    d_ = defaultdict(list)
                    for o_ in ourmarks:
                        d_[o_[0]].append(o_[1])
                    d_ = dict(d_)
                    _logger.warning(f'"{nam}" has a mark of {ma}'
                                    f'\n  this is a {deltapcavg_:.2f}% gap v/s {avg_} average'
                                    f' (sd = {sd_:.2f} [{100 * sd_ / avg_:.2f}%])'
                                    f'\n  {deltapcmin_:.2f}%, {deltapcmax_:.2f}% gap v/s min = {min_}, max = {max_}'
                                    f'\n  data set: {d_}')
                    nfalse += 1
            else:
                nmiss += 1
                missed.append((nam, [(o[0], o[1]) for o in ourmarks]))

        return stats, missed


def get_mark_json(cpu_str: str, marksfile: str = _DEFAULTMARKSFILE) -> str:
    """Return CPU mark assessment as JSON string"""
    try:
        ca = CpuAssessor(marksfile)
        ma, (meth, nline, line), det = ca.assess(cpu_str)

        result = {
            "error": False,
            "mark": str(ma),
            "cpustr": cpu_str,
            "hint": meth.name,
            "cpuscsv": os.path.basename(marksfile),
            "linenum": str(nline),
            "line": str(line),
            "details": det
        }
    except Exception as e:
        result = {
            "error": True,
            "message": str(e)
        }

    return json.dumps(result)


if __name__ == "__main__":

    class MyFormatter(argparse.MetavarTypeHelpFormatter, argparse.RawTextHelpFormatter):
        """Special formatter of mine"""
        # argparse.ArgumentDefaultsHelpFormatter,
        # pass


    epilog_ = fr"""


    ====== Utilisation ======

    Le but de ce script est de donner l'indice CPU pour le CPU passé en paramètre sous forme
    de chaîne de caractères issue, sans doute, du BIOS.

    Par défaut, la recherche se fait dans le fichier {_DEFAULTMARKSFILE} du répertoire courant,
    s'il existe. L'utilisateur peut en spécifier un autre.

    Exemple:

      python ...{os.sep}get_mark_of_cpu.py 'chaîne de caractère'
        ==> renvoie une valeur entière positive, nulle si le CPU n'a pas été trouvé

      Note: "..." désigne le chemin vers le répertoire où est installé le script

    """

    experthelp_ = fr"""
    ======== Usages spéciaux ========

    ==== Utiliser un fichier de notes alternatif ====

      python ...{os.sep}get_mark_of_cpu.py --cpuscsv=<chemin_vers_fichier_de_notes> --cpudesc="chaîne de caractères"

    ==== Tester massivement l'algorithme ====

    Ce mode permet de lancer un test massif de l'algorithme en comparant un jeu de notes obtenues
    précédemment (par d'autres moyens) aux notes obtenues par notre algorithme pour les mêmes CPU.

    Il prend comme entrée supplémentaire un fichier JSON qui contient le jeu de notes existantes et
    en option, un seuil de détection, exprimé en pourcentage.

    Ce fichier JSON doit contenir un dictionnaire structuré comme suit:
        "chaîne identifiant le CPU": [
          [note1, "source de la note1"],
          [note2, "source de la note2"],
          ...
          [noteN, "source de la noteN"],
        ],

        "Intel(R) Core(TM) i7-7500U CPU @ 2.70GHz": [
          [3641, "BXPC24-0264/BXPC24-0264-bolc2.csv"],
          [3635, "SDPC25-0134/SDPC25-0134-bolc2.csv"],
          [3630, "VIPC25-0160/VIPC25-0160-bolc2.csv"]
        ],
        "Intel(R) Core(TM) i7-8650U CPU @ 1.90GHz": [
          [6200, "BXPC24-0271/BXPC24-0271-bolc2.csv"],
          [6219, "BXPC24-0552/BXPC24-0552-bolc2.csv"],
          ...
        ]
    """

    parser_ = argparse.ArgumentParser(description="Trouver la note d'un CPU donné",
                                      epilog=epilog_, add_help=False, formatter_class=MyFormatter)

    parser_.add_argument('-h', '--help', action='help', help="Afficher ce message et quitter")

    parser_.add_argument('--helpall', default=False, action='store_true',
                         help="(expert) Afficher l'aide experte")

    parser_.add_argument("-c", '--cpudesc', type=str,
                         required='--test' not in sys.argv and '--helpall' not in sys.argv, metavar="CPU",
                         help='Chaîne décrivant le CPU ("Intel(R) Celeron(R) CPU  J1900  @ 1.99GHz", par exemple)',
                         default="Intel(R) Celeron(R) CPU  J1900  @ 1.99GHz")

    parser_.add_argument('--cpuscsv', type=str, required=False, metavar="FICCSV",
                         help="Fichier CSV de notes, issu du site web [%(default)s]", default=_DEFAULTMARKSFILE)

    parser_.add_argument("-v", "--verbose", default=False, action='store_true', help="Activer le mode verbeux")

    parser_.add_argument("--debug", default=False, action='store_true',
                         help="(expert) Activer le mode mise au point (très verbeux...)")

    parser_.add_argument("--test", default=False, action='store_true', help="(expert) Activer le mode test")

    parser_.add_argument('-s', "--seuil", default=3.0, type=float, help="(expert) Seuil de détection [%(default)s]")

    parser_.add_argument('-n', "--notes-historiques", type=str, required=False, metavar="LMFILE",
                         help="(expert) Fichier JSON de notes calculées autrement", default=_OURCPUNAMESANDMARKS)

    parser_.add_argument("--json", default=False, action='store_true',
                         help="Retourner le résultat au format JSON")

    args_ = parser_.parse_args()

    if args_.helpall:
        print(f"{experthelp_}")
        sys.exit(0)

    if args_.verbose:
        _logger.setLevel(logging.INFO)

    if args_.debug:
        _logger.setLevel(logging.DEBUG)
        for i_ in sorted(vars(args_).items()):
            _logger.info(f'{i_[0]:<12}: {i_[1]}')  # .format(i_[0], i_[1]))

    mfile_ = os.path.realpath(args_.cpuscsv)
    if not os.path.isfile(mfile_) or not os.access(mfile_, os.R_OK):
        _logger.error(f'Impossible de lire le fichier de notes {mfile_}')
        parser_.exit(1)

    cpu_ = args_.cpudesc

    if args_.verbose or args_.debug:
        _logger.info(f'Looking for "{cpu_}" in {mfile_}')

    ca_ = CpuAssessor(mfile_)

    if not args_.test:
        # cpu_ = "Intel(R) Core(TM) i7-9700K CPU @ 3.60GHz"
        ma_, (meth_, nline_, line_), det_ = ca_.assess(cpu_)

        if args_.json:
            result_ = {
                "error": True if ma_ == 0 else False,
                "mark": str(ma_),
                "cpustr": cpu_,
                "hint": meth_.name,
                "cpuscsv": os.path.basename(mfile_),
                "linenum": str(nline_),
                "line": str(line_),
                "details": det_
            }
            print(json.dumps(result_))
        else:
            print(f'"{cpu_}" a pour indice: {ma_} ({meth_}, {nline_}, "{line_}")')
    else:
        lmfile_ = os.path.realpath(args_.notes_historiques)
        if not os.path.isfile(lmfile_) or not os.access(lmfile_, os.R_OK):
            _logger.error(f'Impossible de lire le fichier de notes tierces {lmfile_}')
            parser_.exit(2)

        threshold_ = args_.seuil
        stats_, missed_ = ca_.test(lmfile_, threshold_)
        print(stats_, missed_)

    sys.exit(0)

# -c "Intel(R) Celeron(R) CPU  J1900  @ 1.99GHz" --cpus-csv /home/ghalebp/tmp/audit/cpumarks.csv
