#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK

import time
import logging
import argparse
import argcomplete

from manpage.directory import ManDirectoryParser


def dirparse(args):
    parser = ManDirectoryParser(database=args.database)
    parser.parse_directory(source_dir=args.source_dir)

    mps = args.missing_parsers

    if mps:
        print "Top %s missing parsers: %s" % (
            mps, parser.missing_parsers.most_common(mps))


def generate(args):
    parser = ManDirectoryParser(database=args.database)
    parser.generate_output(output_dir=args.output_dir, base_url=args.base_url)

    scs = args.section_counters
    if scs:
        print "Top %s section names: %s" % (
            scs, parser.section_counters.most_common(scs))

    mls = args.missing_links
    if mls:
        print "Top %s missing links: %s" % (
            mls, parser.missing_links.most_common(mls))


if __name__ == '__main__':
    start_time = time.time()

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--log-level", help="choose log level")
    parser.add_argument(
        "--database",
        help="the database you want to use",
        default="manpages.db")
    subparsers = parser.add_subparsers()

    # dirparse option
    parser_dirparse = subparsers.add_parser(
        'dirparse',
        help='Parses directory into a database',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser_dirparse.add_argument(
        "source_dir", help="the directory you want to use as source")
    parser_dirparse.add_argument(
        "--missing-parsers",
        help="choose the amount of missing parsers to display",
        type=int,
        default=0)

    parser_dirparse.set_defaults(func=dirparse)

    # generate option
    parser_generate = subparsers.add_parser(
        'generate',
        help='Generates pages from database',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser_generate.add_argument(
        "--base-url", help="Base URL", default="https://www.carta.tech/")
    parser_generate.add_argument(
        "output_dir", help="the directory you want to use as a destination")
    parser_generate.add_argument(
        "--missing-links",
        help="choose the amount of broken links to display",
        type=int,
        default=0)
    parser_generate.add_argument(
        "--section-counters",
        help="choose the amount of section titles to display",
        type=int,
        default=0)

    parser_generate.set_defaults(func=generate)

    # Set bash autocompletion
    argcomplete.autocomplete(parser)

    # Parse arguments
    args = parser.parse_args()

    if args.log_level:
        log_level = getattr(logging, args.log_level.upper())
        logging.basicConfig(level=log_level)

    args.func(args)

    elapsed = time.time() - start_time
    logging.info("--- Total time: %s seconds ---" % (elapsed, ))
