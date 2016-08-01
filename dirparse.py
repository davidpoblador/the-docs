#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging

from manpage.directory import ManDirectoryParser


def dirparse(args):
    parser = ManDirectoryParser(database=args.database)
    parser.parse_directory(source_dir=args.source_dir)


def generate(args):
    parser = ManDirectoryParser(database=args.database)
    parser.generate_output(output_dir=args.output_dir, base_url=args.base_url)


def stats(args):
    parser = ManDirectoryParser(database=args.database)
    # FIXME
    #parser.add_argument("--missing-links",
    #                    help="choose the amount of broken links to display",
    #                    type=int,
    #                    default=10)
    #parser.add_argument("--missing-parsers",
    #                    help="choose the amount of missing parsers to display",
    #                    type=int,
    #                    default=10)
    #parser.add_argument("--section-counters",
    #                    help="choose the amount of section titles to display",
    #                    type=int,
    #                    default=10)

    #parser.number_missing_links = args.missing_links
    #parser.number_section_counters = args.section_counters
    #parser.number_missing_parsers = args.missing_parsers
    #

    #print "Missing Links: %s" % parser.get_missing_links()
    #print "Missing Parsers: %s" % parser.get_missing_parsers()
    #print "Pages With Missing Parsers", parser.get_pages_with_missing_parsers()
    #print "Section Counter", parser.get_section_counters()
    pass


if __name__ == '__main__':
    import time
    import argparse
    start_time = time.time()

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--log-level", help="choose log level")
    parser.add_argument("--database",
                        help="the database you want to use",
                        default="manpages.db")
    subparsers = parser.add_subparsers()

    # dirparse option
    parser_dirparse = subparsers.add_parser(
        'dirparse',
        help='Parses directory into a database',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser_dirparse.add_argument(
        "source_dir",
        help="the directory you want to use as source")
    parser_dirparse.set_defaults(func=dirparse)

    # generate option
    parser_generate = subparsers.add_parser(
        'generate',
        help='Generates pages from database',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser_generate.add_argument("--base-url",
                                 help="Base URL",
                                 default="https://www.carta.tech/")

    parser_generate.add_argument(
        "output_dir",
        help="the directory you want to use as a destination")
    parser_generate.set_defaults(func=generate)

    # statistics
    parser_stats = subparsers.add_parser(
        'stats',
        help='Get statistics about the current parsing state',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser_stats.set_defaults(func=stats)

    # Parse arguments
    args = parser.parse_args()

    if args.log_level:
        log_level = getattr(logging, args.log_level.upper())
        logging.basicConfig(level=log_level)

    args.func(args)

    elapsed = time.time() - start_time
    logging.info("--- Total time: %s seconds ---" % (elapsed, ))
