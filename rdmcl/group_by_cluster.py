#!/usr/bin/env python3
# -*- coding: utf-8 -*-# Created on: Aug 15 2017

"""
Output the description line for each record in each cluster, neatly organized as a group
"""

try:
    from rdmcl.compare_homolog_groups import prepare_clusters
except ImportError:
    from compare_homolog_groups import prepare_clusters

from buddysuite import SeqBuddy as Sb
from buddysuite import AlignBuddy as Alb
import re
import sys
from collections import OrderedDict
import os


def make_msa(cluster, aligner, trimal):
    trimal = trimal if trimal else ["clean"]

    if len(cluster) < 2:
        alignment = cluster
    else:
        alignment = Alb.generate_msa(Sb.make_copy(cluster), aligner, quiet=True)
        ave_seq_length = Sb.ave_seq_length(cluster)
        for threshold in trimal:
            align_copy = Alb.trimal(Alb.make_copy(alignment), threshold=threshold)
            cleaned_seqs = Sb.clean_seq(Sb.SeqBuddy(str(align_copy)))
            cleaned_seqs = Sb.delete_small(cleaned_seqs, 1)
            # Structured this way for unit test purposes
            if len(alignment.records()) != len(cleaned_seqs):
                continue
            elif Sb.ave_seq_length(cleaned_seqs) / ave_seq_length < 0.5:
                continue
            else:
                alignment = align_copy
                break
    return alignment


def main():
    import argparse

    parser = argparse.ArgumentParser(prog="group_by_cluster", description="",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument("clusters", action="store", help="path to clusters file")
    parser.add_argument("sequence_file", action="store", help="path to original sequence file")
    parser.add_argument("mode", action="store", nargs="?", default="list",
                        help="Choose the output type [list, seq, sequences, aln, alignment, con, consensus]")
    parser.add_argument("--aligner", "-a", action="store", default="clustalo",
                        help="Specify a multiple sequence alignment program")
    parser.add_argument("--groups", "-g", action="append", nargs="+", help="List the specific groups to process")
    parser.add_argument("--max_group_size", "-max", action="store", type=int, help="Max cluster size to process")
    parser.add_argument("--min_group_size", "-min", action="store", type=int, help="Min cluster size to process")
    parser.add_argument("--trimal", "-trm", action="append", nargs="*", help="Specify trimal parameters",
                        default=["gappyout", 0.5, 0.75, 0.9, 0.95, "clean"])
    parser.add_argument("--write", "-w", action="store", help="Specify directory to write file(s)")
    in_args = parser.parse_args()

    mode = in_args.mode.lower()
    mode = "seq" if "sequences".startswith(mode) else mode
    mode = "aln" if "alignment".startswith(mode) else mode
    mode = "con" if "consensus".startswith(mode) else mode
    mode = "list" if "list".startswith(mode) else mode

    if in_args.groups:
        in_args.groups = [x.lower() for x in in_args.groups[0]]
        in_args.groups = "^%s$" % "$|^".join(in_args.groups)

    cluster_file = prepare_clusters(in_args.clusters, hierarchy=True)
    seqbuddy = Sb.SeqBuddy(in_args.sequence_file)
    output = OrderedDict()

    for rank, node in cluster_file.items():
        rank = rank.split()[0]
        if in_args.groups:
            if not re.search(in_args.groups, rank):
                continue

        node = [x.split("-")[1] for x in node]
        if in_args.min_group_size:
            if len(node) < in_args.min_group_size:
                continue

        if in_args.max_group_size:
            if len(node) > in_args.max_group_size:
                continue

        ids = "%s$" % "$|".join(node)
        subset = Sb.pull_recs(Sb.make_copy(seqbuddy), ids)
        subset = Sb.order_ids(subset)

        rank_output = ""
        if mode == "list":
            rank_output += rank
            for rec in subset.records:
                rec.description = re.sub("^%s" % rec.id, "", rec.description)
                rank_output += "\n%s %s" % (rec.id, rec.description)
            rank_output += "\n"

        elif mode == "seq":
            for rec in subset.records:
                rec.description = "%s %s" % (rank, rec.description)
            rank_output += str(subset)

        elif mode in ["aln", "con"]:
            try:
                rank_output = make_msa(subset, in_args.aligner, in_args.trimal)
            except (SystemError, AttributeError) as err:
                print(err)
                sys.exit()
            rank_output.out_format = "phylip-relaxed"

        if mode == "con":
            rec = Alb.consensus_sequence(rank_output).records()[0]
            rec.id = rank
            rec.name = rank
            rec.description = ""
            rank_output.out_format = "fasta"

        output[rank] = str(rank_output)

    if not in_args.write:
        print("\n".join(data for rank, data in output.items()).strip())

    else:
        outdir = os.path.abspath(in_args.write)
        os.makedirs(outdir, exist_ok=True)
        extension = ".%s" % seqbuddy.out_format[:3] if mode == "seq" \
            else ".txt" if mode == "list" \
            else ".phy" if mode == "aln" \
            else ".fa"

        for rank, data in output.items():
            with open(os.path.join(outdir, rank + extension), "w") as ofile:
                ofile.write(data)


if __name__ == '__main__':
    main()