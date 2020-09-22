#encoding: UTF-8

from functools import wraps
import inspect
from copy import deepcopy
from bs4 import BeautifulSoup
from os.path import basename,dirname,splitext,isfile,join
from shutil import copy2,rmtree
from subprocess import call
import os,argparse,errno
import sys
import re
import glob
import pdb
import csv
from natsort import natsorted
from typing import List
import yaml

## This program converts Taiwan driver's test PDF files into csv for import as Anki flashcards. It can optionally copy images to Anki media folder


def main():
  scriptDir=os.path.dirname(os.path.realpath(__file__))
  parser = argparse.ArgumentParser()
  parser.add_argument('-f', '--file', required=True, help='PDF file from DMV, or its poppler-converted XML file')
  parser.add_argument('-v', '--vehicle', choices=['car','moto','mech'])
  parser.add_argument('-s', '--signsrules', choices=['signs','rules'])
  parser.add_argument('-l', '--language', choices=['english','chinese','vietnamese','khmer','japanese','indonesian','thai','burmese'])
  parser.add_argument('-t', '--truechoice', choices=['true','choice'])
  parser.add_argument('-a', '--ankimedia', help='Path to anki media folder.  If set, copy images there')
  parser.add_argument('-e', '--ankiexport', help='Anki export containing labels.  Set to empty string to skip applying labels', default=scriptDir+'/input/All Decks.txt')
  parser.add_argument('-w', '--working', default='./',help='Path where CSV and intermediate files will be written')
  parser.add_argument('-o', '--overwrite', action='store_true', help='Recreate and overwrite CSV file even if it already exists.')
  parser.add_argument('-d', '--dontdelete', action='store_true', help='Do not delete intermediate files after running.')
  args = parser.parse_args()

  filename = splitext(basename(args.file))
  base = filename[0]
  ext = filename[1]
  xmlfile = args.file

  qfile = QuestionFile(filebase=base,
                       language=args.language,
                       vehicle=args.vehicle,
                       signsrules=args.signsrules,
                       truechoice=args.truechoice,
                       ankiexport=args.ankiexport)

  workingDir = args.working + '/' + qfile.getFileID()
  mkdir_p(workingDir)

  outputFile = join(args.working,qfile.getFileID()+'.csv')
  if not args.overwrite and isfile(outputFile):
    print("%s exists" % (outputFile))
    sys.exit()
  if ext == '.pdf':
    xmlfile = workingDir + '/' + base + '.xml'
    opts = ['pdftohtml', '-xml']
    if not args.ankimedia:
      opts.append('-i')
    opts.extend([args.file, xmlfile])
    FNULL = open(os.devnull, 'w')
    call(opts,stdout=FNULL)
  elif ext != '.xml':
    warning("File [-f file] is not .xml or .pdf")
    sys.exit()

  filehandler = open(xmlfile)

  soup = BeautifulSoup(filehandler,'lxml')

  current_q = qfile.newQuestion()

  state = ''
  qnum = 0

  ignorable_lines = [ '^題號$',
                      '^答案$',
                      '^題目圖示$',
                      '^題\s*目$',
                      '^第\d+頁/共\d+頁$',
                      '^機車標誌、標線、號誌..題$',
                      '^分類$',
                      '^編號$',
                      '^機車法規選擇題$',
                      '^機車法規是非題$',
                      '^汽車法規選擇題$',
                      '^【英文】$',
                      '^汽車法規是非題$',
                      '^汽車標誌、標線、號誌.含汽車儀表警示、指示燈...題$',
                      '^分類編號$',
                      '^分類編$',
                      '^號$',
                      '^題號答案$',
                    ]


  for page in soup.findAll('page'):
    pageheight = int(page['height'])
    pagewidth = int(page['width'])
    for text in page.findAll('text'):
      top_pos = float(text['top']) / pageheight
      left_pos = float(text['left']) / pagewidth
      txt = text.get_text()
      txt_strip = txt.strip()
      txt_nospace = re.sub('\s+','',txt)
      if not txt_strip:
        continue
      skip = False
      for ignore in ignorable_lines:
        if re.match(ignore, txt_nospace):
          skip = True
          continue
      if skip:
        continue
      if re.match('^[0-9]{3}$',txt_strip):
        state = 'found_qnum'
        qnum = int(txt_strip)
        qnum_i = qnum-1
        if current_q:
          current_q.question = re.sub('\n','',current_q.question)
          current_q = qfile.newQuestion()
        current_q.number = qnum
        continue
      elif state == 'found_qnum':
        if re.match('^[0-9OX]$',txt_strip) or txt_strip == 'Ｘ' or txt_strip == 'Ｏ':
          state = 'found_ans'
          if current_q.answer != '':
            warning("%d: Answer being overwritten" % (qnum))
          if txt_strip == 'Ｏ': txt_strip = 'O'
          elif txt_strip == 'Ｘ': txt_strip = 'X'
          current_q.answer = txt_strip
        else:
          warning("%d: Answer not found after question number" % (qnum))
      elif state == 'found_ans' and not re.match('^[0-9]+$',txt_strip):
        current_q.question += txt
      elif re.match('^[0-9]{1,2}$',txt_strip) and left_pos > 0.75:
        current_q.category = txt_strip
  filehandler.close()

  qfile.writeCSV(args.working)
  if args.ankimedia:
    qfile.copyImages(workingDir, args.ankimedia)
  if not args.dontdelete:
    rmtree(workingDir)

def initializer(func):
  names, varargs, keywords, defaults = inspect.getargspec(func)

  @wraps(func)
  def wrapper(self, *args, **kargs):
    for name, arg in list(zip(names[1:], args)) + list(kargs.items()):
      setattr(self, name, arg)

    for name, default in zip(reversed(names), reversed(defaults)):
      if not hasattr(self, name):
        setattr(self, name, default)

    func(self, *args, **kargs)

  return wrapper


class TagMap:
  """
  Maps from `question` instances to their associated tags.

  Currently the only tags we have are for the difficulty: "easy", "medium", "hard", and "impossible".
  """
  class QuestionAnswerTags:
    def __init__(self, question: str, answer: str, tags: List[str]):
      self.question = question
      self.answer = answer
      self.tags = tags

    def __repr__(self):
      attrs = ['question', 'answer', 'tags']
      pieces = []
      for attr in attrs:
        pieces.append('{}={}'.format(attr, repr(getattr(self, attr))))
      return '{}({})'.format(self.__class__.__name__, ', '.join(pieces))

  def __init__(self, question_answer_tags: List[QuestionAnswerTags]):
    self._q_and_a_to_tags = {}
    for qatag in question_answer_tags:
      key = self._key(qatag.question, qatag.answer)
      self._q_and_a_to_tags[key] = qtag.tags

  @classmethod
  def load_from_yaml(cls, yaml_file_path):
    with open(yaml_file_path) as f:
      data = yaml.load(f)

    qatags = []
    for entry in data:
      qatags.append(QuestionAnswerTags(question=entry['question'], answer=str(entry['answer']), tags=entry['tags']))

    return cls(qatags)

  @classmethod
  def _normalize(cls, question: str) -> str:
    question = question.sub('<br/>', ' ')
    question = re.sub(question, ' +', ' ')
    question = question.strip()
    return question

  @classmethod
  def _key(cls, question: str, answer: str) -> str:
    return cls._normalize(question) + '|' + answer

  def get_tags(self, question: Question) -> List[str]:
    """
    Returns list of tags, or None if there are no tags for the given question defined in the YAML file.
    """
    return self._q_and_a_to_tags.get(self._key(question.question, question.answer))


## QuestionFile is used to build up an object and export to CSV.
## There is currently no import function
class QuestionFile(object):
  global filemap
  filemap = {
              '機車法規是非題-中文' : ('moto', 'rules', 'true','chinese'),
              '機車法規選擇題-中文' : ('moto', 'rules', 'choice', 'chinese'),
              '機車標誌是非題-中文' : ('moto', 'signs', 'true','chinese'),
              '機車標誌選擇題-中文' : ('moto', 'signs', 'choice','chinese'),
              '汽車標誌是非題-中文' : ('car', 'signs', 'true', 'chinese'),
              '汽車標誌選擇題-中文' : ('car', 'signs', 'choice', 'chinese'),
              '汽車法規是非題-中文' : ('car', 'rules', 'true', 'chinese'),
              '汽車法規選擇題-中文' : ('car', 'rules', 'choice', 'chinese'),
              '機車法規是非題-英文1090116' : ('moto', 'rules', 'true', 'english'),
              '機車法規選擇題-英文1090116' : ('moto', 'rules', 'choice', 'english'),
              'Signs-True or False／English〈機車標誌是非題-英文〉' : ('moto', 'signs', 'true', 'english'),
              'Signs-Choice／English〈機車標誌選擇題-英文〉' : ('moto', 'signs', 'choice', 'english'),
              'Rules-Choice／English(汽車法規選擇題-英文)' : ('car', 'rules', 'choice', 'english'),
              'Rules-True or False／English(汽車法規是非題-英文)' : ('car', 'rules', 'true', 'english'),
              'Signs-Choice／English(汽車標誌選擇題-英文)' : ('car', 'signs', 'choice', 'english'),
              'Signs-True or False／English(汽車標誌是非題-英文)' : ('car', 'signs', 'true', 'english'),
            }

  for k in list(filemap):
    v = filemap[k]
    id=v[3]+'-'+v[0]+'-'+v[1]+'-'+v[2]
    filemap[id] = v

  @initializer
  def __init__(self,filebase='',language='',vehicle='',signsrules='',truechoice='',questions=[],images=[],ankiexport=''):
    attributes_set = (language and vehicle and signsrules and truechoice)
    if attributes_set:
      pass
    elif filebase in filemap:
      (self.vehicle, self.signsrules, self.truechoice, self.language) = filemap[filebase]
    else:
      if filebase:
        #warning('Unsupported filebase: '+filebase)
        pass
      else:
        warning('qfile(): Must set all attributes or filebase.')
      sys.exit()
    if ankiexport:
      self.readLabels()

    self.tag_map = self.readTagMap()

  def readLabels(self):
    self.labels = {}
    with open(self.ankiexport) as f:
      reader = csv.reader(f, delimiter='\t')
      for line in reader:
        id = line[0]
        tag = line[-1]
        self.labels[id] = tag

  def readTagMap(self):
    if not os.path.exists('inputs/tags'):
      raise RuntimeError('Directory inputs/tags does not exist; did you run this from the root of the repo?')

    yaml_path = os.path.join('inputs/tags', '{}-{}-{}-{}.yaml'.format(self.language, self.vehicle, self.signsrules, self.truechoice)
    if not os.path.exists(yaml_path):
      return None

    return TagMap.load_from_yaml(yaml_path)

  def getFileID(self):
    return self.language+'-'+self.vehicle+'-'+self.signsrules+'-'+self.truechoice
  def newQuestion(self):
    q = Question(qfile=self)
    self.questions.append(q)
    return q
  def getQuestion(self,i):
    return self.questions[i]
  def prettyAll(self):
    self.finished()
    return '\n'.join(q.pretty() for q in self.questions)+'\n'
  def writeCSV(self, dir):
    file = dir + '/' + self.getFileID() + '.csv'
    f = open(file, 'w')
    f.write(self.prettyAll())
    f.close()
    print("Wrote file: "+file)
  def finished(self):
    lastq = self.questions[-1]
    if not lastq:
      del self.questions[-1]
    if self.signsrules == 'signs':
      self.populateImageNames()
      for i,q in enumerate(self.questions):
        q.question = '<img src="'+self.images[i]+'"/><br/>'+q.question
    self.finished_called = 1
  def copyImages(self, work, anki):
    if not self.finished_called:
      self.finished()
    images = [f for f in glob.glob(work + '/' + self.filebase + '*.*') if not re.match('.*\.xml', f)]
    for i,f in enumerate(natsorted(images)):
      copy2(f, anki + '/' + self.images[i])
  def populateImageNames(self):
    self.images = []
    newbase = self.getFileID()
    for i,q in enumerate(self.questions):
      qnum = i+1
      imagefile = newbase+'-'+str(qnum)+'.png'
      self.images.append(imagefile)

class Question(object):
  @initializer
  def __init__(self,number='',question='',answer='',category='', qfile=''):
    pass

  def __repr__(self):
    attrs = ['number', 'question', 'answer', 'category', 'qfile']
    pieces = []
    for attr in attrs:
      pieces.append('{}={}'.format(attr, repr(getattr(self, attr))))
    return '{}({})'.format(self.__class__.__name__, ', '.join(pieces))

  def __eq__(self, other):
    copy_self = deepcopy(self)
    copy_other = deepcopy(other)
    copy_self.qfile = ''
    copy_other.qfile = ''
    return (isinstance(copy_other, copy_self.__class__) and copy_self.__dict__ == copy_other.__dict__)
  def __ne__(self, other):
    return not self.__eq__(other)
  def __bool__(self):
    empty = Question()
    mycopy = deepcopy(self)
    mycopy.qfile = ''
    return self != empty
  __nonzero__ = __bool__
  def add_question_text(self):
    pass
  def pretty(self):
    if not self.number or not self.question or not self.answer:
      warning("pretty(): Number, question or answer not set before printing")
    pretty_question = self.question
    if self.qfile.truechoice == 'choice':
      pretty_question = re.sub(r'\( *([123]) *\)',r'<br/>(\1) ',self.question)

    num_matching = self.number
    #The question # 165 that appears in the english test doesn't appear in the Chinese version.
    # So, the english version is ahead by one number until the end (#633)
    # 2 extra questions only appear in the Chinese version at the end of the file.

    # This logic is replicated in produceHTML.py
    if self.qfile.getFileID() == 'chinese-car-rules-true' and self.number >= 165:
      num_matching += 1
    fillNum_matching = str(num_matching).zfill(3)
    fileID_and_num_matching = self.qfile.getFileID()+'-'+fillNum_matching

    fillNum = str(self.number).zfill(3)
    fileID_and_num = self.qfile.getFileID()+'-'+fillNum
    row = [fileID_and_num,pretty_question,self.answer,self.category,
           self.qfile.language, self.qfile.vehicle, self.qfile.signsrules, self.qfile.truechoice]
    englishID = fileID_and_num_matching.replace(self.qfile.language,'english')
    #anyID = fileID_and_num.replace(self.qfile.language,'any')

    # Always overriding label with the one in the english set
    if self.qfile.tag_map is not None:
      tags = self.qfile.tag_map.get_tags(self)
      if tags is None:
        raise RuntimeError('no tags for question {}'.format(self))
    else:
      tags = [self.qfile.labels.get(englishID,'')]

    #label = self.qfile.labels.get(fileID_and_num,'')
    #if not label:

      #label = self.qfile.labels.get(anyID,'')
    row.append(','.join(tags))
    return '\t'.join(row)

def warning(*objs):
  print("WARNING: ", *objs, file=sys.stderr)

def mkdir_p(path):
  try:
    os.makedirs(path)
  except OSError as exc: # Python >2.5
    if exc.errno == errno.EEXIST and os.path.isdir(path):
      pass
    else: raise


if __name__ == '__main__':
  main()
