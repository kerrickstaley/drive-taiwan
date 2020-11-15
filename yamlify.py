#!/usr/bin/env python3
import argparse
import yaml
import sys

parser = argparse.ArgumentParser()
parser.add_argument('prefix')


def main(args):
    output = []
    with open('input/All Decks.txt') as f:
        for line in f:
            if not line.startswith(args.prefix):
                continue

            pieces = line.strip().split('\t')

            output.append({
                'question': pieces[1],
                'answer': pieces[2],
                'difficulty': pieces[9],
            })

    yaml.dump(output, sys.stdout)


if __name__ == '__main__' and not hasattr(sys, 'ps1'):
    main(parser.parse_args())
