"""Implements the sequence to update the CSV marks file"""
import os
import sys
import json
import time
import datetime
from pathlib import Path as plPath

from cpu_marks_db import CpuMarks, write_csvfile


def update_now(current_marks: str):  # -> dict[str, str]:
    """Creates a new marks DB and move the main symbolic link to point on it"""
    # If current_marks is <PATH>/cpumarks-20251006.104052.csv,
    # we know that <PATH>/cpumarks.csv is a symbolic link like: cpumarks.csv -> cpumarks-20251006.104052.csv
    # We want to:
    #   -create <PATH>/cpumarks-{datestamp}}.csv
    #   -move cpumarks.csv to link to cpumarks-{datestamp}.csv
    datestamp = time.strftime("%Y%m%d.%H%M%S", datetime.datetime.now().timetuple())
    new_marks = ''
    d = []
    try:
        marks = CpuMarks()
        d = marks.get_cpu_list()
        new_marks_name = f"cpumarks-{datestamp}.csv"
        marks_dir = os.path.dirname(current_marks)
        new_marks = os.sep.join([marks_dir, new_marks_name])
        write_csvfile(d, new_marks, fieldlist=marks.get_field_list())
        link_full_name = plPath(os.sep.join([marks_dir, "cpumarks.csv"]))
        if link_full_name.is_symlink() or link_full_name.exists():
            link_full_name.unlink()
        link_full_name.symlink_to(plPath(new_marks_name))
    except Exception as exc:  # pylint: disable=W0718
        status = "failure"
        reason = f'{exc}'
    else:
        status = "success"
        reason = ''

    return {"status": status, "reason": reason,
            "newmarksfile": f'{os.path.basename(new_marks)}', "newmarksnum": f'{len(d)}'}


if __name__ == "__main__":
    marksfile_ = os.path.realpath(os.sep.join([os.path.dirname(__file__), 'cpumarks.csv']))
    # print(marksfile_)
    ret_ = update_now(marksfile_)
    print(json.dumps(ret_))
    sys.exit(0)
