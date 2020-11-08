#!/usr/bin/env python3
import csv
import yaml
import sys

with open('Taiwan Motorcycle_Scooter _ Car Exam Questions - Copy of Car - Rules - Multiple Choice.tsv') as tsvfile:
    reader = csv.DictReader(tsvfile, delimiter='\t')

    output_yaml = []

    for line in reader:
        if line['Official Answer'] == 'x':
            continue
        output_yaml.append({
            'question': line['Question'],
            'answer': int(line['Official Answer']),
            'tags': [['INVALID', 'easy', 'medium', 'hard', 'impossible'][int(line['Difficulty Rating (1-4)'])]],
        })


yaml.dump(output_yaml, sys.stdout, sort_keys=False)
