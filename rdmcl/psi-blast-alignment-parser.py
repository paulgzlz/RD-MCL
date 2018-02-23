#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Created on: Apr 22 2015

"""
Convert the 'Flat query-anchored with letters for identities' alignment output, as generated by NCBI PSI-BLAST
server, into FASTA.
"""

import re
import argparse
import os
from io import StringIO
from collections import OrderedDict
from tempfile import TemporaryFile
from math import floor

VERSION = "1.0"


# Credit to rr- (http://stackoverflow.com/users/2016221/rr)
# http://stackoverflow.com/questions/18275023/dont-show-long-options-twice-in-print-help-from-argparse
class CustomHelpFormatter(argparse.RawDescriptionHelpFormatter):
    def _format_action_invocation(self, action):
        if not action.option_strings or action.nargs == 0:
            return super()._format_action_invocation(action)
        default = self._get_default_metavar_for_optional(action)
        args_string = self._format_args(action, default)
        return ', '.join(action.option_strings) + ' ' + args_string


class Match(object):
    def __init__(self, rec_id, block_len, query_len):
        self.id = rec_id
        self.block_len = block_len
        self.query_len = query_len
        self.sequence = ["-" * block_len for _ in range(int(floor(query_len / block_len)))]
        if query_len % block_len:
            self.sequence.append("-" * (query_len % block_len))
        self.end = None

    def fasta(self):
        return ">%s\n%s\n" % (self.id, "".join(self.sequence))

    def update_seq(self, indx, seq, end):
        # Ensure the input sequence is correctly sized
        assert len(seq) == len(self.sequence[indx])
        self.sequence[indx] = seq
        self.end = end
        return

    def __str__(self):
        return self.fasta()


def argparse_init():
    def fmt(prog):
        return CustomHelpFormatter(prog)

    parser = argparse.ArgumentParser(prog="psi-blast-alignment-parser", formatter_class=fmt, add_help=False,
                                     usage=argparse.SUPPRESS, description='''\
\033[1mPSI-Blast Alignment Parser\033[m
  Because ugh... It's hard to parse.

  Convert the 'Flat query-anchored with letters for identities' alignment output, as generated by NCBI PSI-BLAST
  server, into FASTA.
  
\033[1mUsage\033[m:
  psi-blast-alignment-parser input_file
''')

    # Positional
    positional = parser.add_argument_group(title="\033[1mPositional argument\033[m")

    positional.add_argument("input_file", help="Input file (path or stdin)", action="store")

    # Misc
    misc = parser.add_argument_group(title="\033[1mMisc options\033[m")
    misc.add_argument('-v', '--version', action='version', version=VERSION)
    misc.add_argument('-h', '--help', action="help", help="Show this help message and exit")

    in_args = parser.parse_args()
    return in_args


def main():
    in_args = argparse_init()

    if str(type(in_args.input_file)) == "<class '_io.TextIOWrapper'>":
        if not in_args.input_file.seekable():  # Deal with input streams (e.g., stdout pipes)
            input_txt = in_args.input_file.read()
            temp = StringIO(input_txt)
            in_args.input_file = temp
        in_args.input_file.seek(0)
        data = in_args.input_file.read()

    elif type(in_args.input_file) == str and os.path.isfile(in_args.input_file):
        file_path = str(in_args.input_file)
        with open(file_path, "r") as ifile:
            data = ifile.read()
    else:
        data = in_args.input_file

    blocks = re.findall("Query[^=]*?\n\n|Query[^=]*$", data, re.DOTALL)
    for i, block in enumerate(blocks):
        block = block.strip().split("\n")
        for j, line in enumerate(block):
            front = line[:20].split()
            front = [front[0], int(front[1])] if len(front) == 2 else [front[0], None]
            back = line[20:]
            if back.endswith(" "):
                back = [back[:-2], None]
            else:
                back = re.search("(.*)? {2}([0-9]+)", back)
                back = [back.group(1), int(back.group(2))]
            back[0] = re.sub(" ", "-", back[0])
            line = front + back
            block[j] = line
        blocks[i] = block

    block_len = len(blocks[0][0][2])
    query_len = block_len * (len(blocks) - 1) + (len(blocks[-1][0][2]))

    output = OrderedDict()
    for b_indx, block in enumerate(blocks):
        for line in block:
            rec_id, start, seq, end = line
            if start is None:
                continue
            output.setdefault(rec_id, [])
            make_new = True
            for match in output[rec_id]:
                if match.end is not None and match.end + 1 == start:
                    match.update_seq(b_indx, seq, end)
                    make_new = False
                    break
            if make_new:
                match = Match(rec_id, block_len, query_len)
                match.update_seq(b_indx, seq, end)
                output[rec_id].append(match)

    temp_file = TemporaryFile()
    for rec_id, matches in output.items():
        for match in matches:
            temp_file.write(match.fasta().encode())

    temp_file.seek(0)
    print(temp_file.read().decode())


if __name__ == '__main__':
    main()
