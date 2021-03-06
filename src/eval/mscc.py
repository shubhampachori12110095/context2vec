'''
The function create_mscc_dataset is Copyright 2016 Oren Melamud
Modifications copyright (C) 2018 Tatsuya Aoki

This code is based on https://github.com/orenmel/context2vec/blob/master/context2vec/eval/mscc_text_tokenize.py
Used to convert the Microsoft Sentence Completion Challnege (MSCC) learning corpus into a one-sentence-per-line format.
'''

import glob
import numpy
import torch
import sys
import os
from nltk.tokenize import word_tokenize, sent_tokenize


def create_mscc_dataset(input_dir, output_filename, lowercase=True):
    def write_paragraph_lines(paragraph_lines, file_obj):
        paragraph_str = ' '.join(paragraph_lines)
        for sent in sent_tokenize(paragraph_str):
            if lowercase:
                sent = sent.lower()
            file_obj.write(' '.join(word_tokenize(sent))+'\n')

    if input_dir[-1] != '/':
        input_dir += '/'

    if not os.path.isdir(input_dir):
        raise NotADirectoryError

    print('Read files from', input_dir)
    print('Creating dataset to', output_filename)
    files = glob.glob(input_dir + '*.TXT')
    with open(output_filename, mode='w') as output_file:
        for file in files:
            with open(file, mode='r', errors='ignore') as input_file:
                paragraph_lines = []
                for i, line in enumerate(input_file):
                    if len(line.strip()) == 0 and len(paragraph_lines) > 0:
                        write_paragraph_lines(paragraph_lines, output_file)
                        paragraph_lines = []
                    else:
                        paragraph_lines.append(line)
                if len(paragraph_lines) > 0:
                    write_paragraph_lines(paragraph_lines, output_file)
                print('Read {} lines'.format(i))


def read_mscc_questions(input_file, lower=True):
    with open(input_file, mode='r') as f:
        questions = []
        for line in f:
            q_id, text = line.split(' ', 1)
            if lower:
                text = text.lower()
            text = text.strip().split()
            target_word = ''
            for index, token in enumerate(text):
                if token.startswith('[') and token.endswith(']'):
                    target_word = token[1:-1]
                    target_pos = index
            if not target_word:
                raise SyntaxError
            questions.append([text, q_id, target_word, target_pos])
    return questions


def print_mscc_score(gold_q_id: list,
                     q_id_and_sim: tuple):

    assert len(q_id_and_sim) % 5 == 0

    gold = numpy.array(gold_q_id)
    answer = numpy.array([sorted(q_id_and_sim[5*i:5*(i+1)], key=lambda x:x[1], reverse=True)
                          for i in range(int(len(q_id_and_sim)/5))])[:, 0, 0]
    correct_or_not = (gold == answer)
    mid = int(len(correct_or_not) / 2)
    dev = correct_or_not[:mid]
    test = correct_or_not[mid:]

    print('Overall', float(sum(correct_or_not))/len(correct_or_not))
    print('dev', float(sum(dev))/len(dev))
    print('test', float(sum(test))/len(test))


def mscc_evaluation(question_file,
                    answer_file,
                    output_file,
                    model,
                    stoi,
                    unk_token,
                    bos_token,
                    eos_token,
                    device):

        questions = read_mscc_questions(question_file)
        q_id_and_sim = []
        with open(question_file, mode='r') as f, open(output_file, mode='w') as w:
            for question, input_line in zip(questions, f):
                tokens, q_id, target_word, target_pos = question
                tokens[target_pos] = target_word
                tokens = [bos_token] + tokens + [eos_token]
                indexed_sentence = [stoi[token] if token in stoi else stoi[unk_token] for token in tokens]
                input_tokens = \
                    torch.tensor(indexed_sentence, dtype=torch.long, device=device).unsqueeze(0)
                indexed_target_word = input_tokens[0, target_pos+1]
                similarity = model.run_inference(input_tokens, indexed_target_word, target_pos)
                q_id_and_sim.append((q_id, similarity))
                w.write(input_line.strip() + '\t' + str(similarity) + '\n')

        with open(answer_file, mode='r') as f:
            gold_q_id = [line.split(' ', 1)[0] for line in f]

        print_mscc_score(gold_q_id, q_id_and_sim)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Please specify your input directory that contains MSCC dataset.')
        print('(Most of the case the name of the directory might be `Holmes_Training_Data`.)')
        print('sample usage: python src/eval/mscc.py ~/dataset/Holmes_Training_Data/')
        quit()
    create_mscc_dataset(sys.argv[1], 'dataset/mscc_train.txt')
