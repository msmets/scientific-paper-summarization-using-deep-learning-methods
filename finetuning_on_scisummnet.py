# -*- coding: utf-8 -*-
"""Finetuning on ScisummNet

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/19YKcrYEFhXbY_9RdsIDUdldqvfBTvZ_0

Setup
"""

!pip install sentencepiece -q

!pip install transformers -q

!pip install py-rouge

import rouge

import nltk
nltk.download('punkt')

import transformers
import torch
import copy
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.model_selection import train_test_split
from torch import nn,optim
from torch.utils import data
from pylab import rcParams
import matplotlib.pyplot as plt
from matplotlib import rc
from tqdm import tqdm

from transformers import BartTokenizer
from transformers import BartForConditionalGeneration

from torch.utils.data import Dataset

from torch.utils.data import DataLoader

from transformers.models.bart.modeling_bart import shift_tokens_right

RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)
torch.manual_seed(RANDOM_SEED)

!nvidia-smi

# # Setting up the device for GPU usage
from torch import cuda
device = 'cuda' if cuda.is_available() else 'cpu'

"""Data preprocessing and exploration"""

from google.colab import drive 
drive.mount('/content/gdrive')

df = pd.read_csv('/content/gdrive/MyDrive/Colab Notebooks/data/RPdata.csv')
#df = df[['summary','article_content','introduction','conclusion']]
df = df[['summary','article_content','introduction','conclusion','citations_gold','citations_all']]
df.head()

summaries = list()

for i in range(len(df)):
  summary = df.loc[i,"summary"]
  summary_list = summary.split('\n')
  new_summary = ' '.join(summary_list[1:])
  summaries.append(new_summary)
  
df["summary"] = summaries

df.shape

df.info()

df_20 = df[['summary','introduction','citations_all']]
df_20 = df_20.dropna()
df_20 = df_20.reset_index(drop=True)
df_20.shape
length_summary = list()
length_intro = list()
length_citall = list()

for i in range(len(df_20)):
  summary = df_20.loc[i,"summary"]
  summary_list = summary.split()
  length_summary.append(len(summary_list))
  intro = df_20.loc[i,"introduction"]
  intro_list = intro.split()
  length_intro.append(len(intro_list))
  citall = df_20.loc[i,"citations_all"]
  citall_list = citall.split()
  length_citall.append(len(citall_list))


df_length = pd.DataFrame()
df_length["summary"] = length_summary
df_length["intro"] = length_intro
df_length["citall"] = length_citall

df_length.describe()

df_30 = df[['article_content']]
df_30 = df_30.dropna()
df_30 = df_30.reset_index(drop=True)
df_30.shape
length_article_content = list()

for i in range(len(df_30)):
  article_content = df_30.loc[i,"article_content"]
  article_content_list = article_content.split()
  length_article_content.append(len(article_content_list))

df_length = pd.DataFrame()
df_length["article_content"] = length_article_content


df_length.describe()

df_40 = df[['conclusion']]
df_40 = df_40.dropna()
df_40 = df_40.reset_index(drop=True)
df_40.shape
length_conc = list()

for i in range(len(df_40)):
  conc = df_40.loc[i,"conclusion"]
  conc_list = conc.split()
  length_conc.append(len(conc_list))

df_length = pd.DataFrame()
df_length["conc"] = length_conc


df_length.describe()

df_50 = df[['citations_gold']]
df_50 = df_50.dropna()
df_50 = df_50.reset_index(drop=True)
df_50.shape
length_citgold = list()

for i in range(len(df_50)):
  citgold = df_50.loc[i,"citations_gold"]
  citgold_list = citgold.split()
  length_citgold.append(len(citgold_list))

df_length = pd.DataFrame()
df_length["citgold"] = length_citgold


df_length.describe()

df = df.dropna()
df = df.reset_index(drop=True)

df.head()

lengthdf = len(df)

a = list()

for i in range(lengthdf):
  s = ''
  s = df.loc[i,"article_content"] + " " + df.loc[i,"introduction"]
  a.append(s)

df['article_content_intro']  = a

lengthdf = len(df)

a = list()

for i in range(lengthdf):
  s = ''
  s = df.loc[i,"article_content_intro"] + " " + df.loc[i,"conclusion"]
  a.append(s)

df['article_content_intro_conc']  = a

lengthdf = len(df)

a = list()

for i in range(lengthdf):
  s = ''
  s = df.loc[i,"article_content_intro_conc"] + " " + df.loc[i,"citations_gold"]
  a.append(s)

df['article_content_citations']  = a

df = df[['summary','article_content_citations']]

df.shape

df.head()

df.info()

length_summary = list()
length_article_content = list()

for i in range(len(df)):
  summary = df.loc[i,"summary"]
  article_content = df.loc[i,"article_content_citations"]
  summary_list = summary.split()
  article_content_list = article_content.split()
  print(len(summary_list))
  length_summary.append(len(summary_list))
  length_article_content.append(len(article_content_list))

df_length = pd.DataFrame()
df_length["summary"] = length_summary
df_length["article_content"] = length_article_content

df_length.describe()

class CustomDataset(Dataset):

    def __init__(self, dataframe, tokenizer, source_len, summ_len):
        self.tokenizer = tokenizer
        self.data = dataframe
        self.source_len = source_len
        self.summ_len = summ_len
        self.summary = self.data.summary
        self.article_content_citations = self.data.article_content_citations

    def __len__(self):
        return len(self.summary)

    def __getitem__(self, index):
        article_content_citations = str(self.article_content_citations[index])
        article_content_citations = ' '.join(article_content_citations.split())

        summary = str(self.summary[index])
        summary = ' '.join(summary.split())

        source = self.tokenizer.batch_encode_plus([article_content_citations], max_length= self.source_len, pad_to_max_length=True,return_tensors='pt')
        target = self.tokenizer.batch_encode_plus([summary], max_length= self.summ_len, pad_to_max_length=True,return_tensors='pt')

        source_ids = source['input_ids'].squeeze()
        source_mask = source['attention_mask'].squeeze()
        target_ids = target['input_ids'].squeeze()
        target_mask = target['attention_mask'].squeeze()

        return {
            'source_ids': source_ids.to(dtype=torch.long), 
            'source_mask': source_mask.to(dtype=torch.long), 
            'target_ids': target_ids.to(dtype=torch.long),
            'target_ids_y': target_ids.to(dtype=torch.long)
        }

def train(epoch, tokenizer, model, device, loader, optimizer):
    model.train()
    for _,data in enumerate(loader, 0):
        lm_labels = data['target_ids'].to(device, dtype = torch.long)
        y_ids = shift_tokens_right(lm_labels, model.config.pad_token_id,decoder_start_token_id=2)
        lm_labels[lm_labels[:, :] == model.config.pad_token_id] = -100
        
        ids = data['source_ids'].to(device, dtype = torch.long)
        mask = data['source_mask'].to(device, dtype = torch.long)

        outputs = model(input_ids = ids, attention_mask = mask, decoder_input_ids=y_ids, labels=lm_labels)
        loss = outputs[0]
        
        #if _%10 == 0:
            #print(f'Training Loss: loss.item()')wandb.log({"Training Loss": loss.item()})

        if _%500==0:
            print(f'Epoch: {epoch}, Loss:  {loss.item()}')
        
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        # xm.optimizer_step(optimizer)
        # xm.mark_step()

def validate(epoch, tokenizer, model, device, loader):
    model.eval()
    predictions = []
    actuals = []
    with torch.no_grad():
        for _, data in enumerate(loader, 0):
            y = data['target_ids'].to(device, dtype = torch.long)
            ids = data['source_ids'].to(device, dtype = torch.long)
            mask = data['source_mask'].to(device, dtype = torch.long)

            generated_ids = model.generate(
                input_ids = ids,
                attention_mask = mask, 
                max_length=500, 
                num_beams=4,
                repetition_penalty=2.5, 
                length_penalty=1.0, 
                early_stopping=True
                )
            preds = [tokenizer.decode(g, skip_special_tokens=True, clean_up_tokenization_spaces=True) for g in generated_ids]
            target = [tokenizer.decode(t, skip_special_tokens=True, clean_up_tokenization_spaces=True)for t in y]
            if _%100==0:
                print(f'Completed {_}')

            predictions.extend(preds)
            actuals.extend(target)
    return predictions, actuals

def prepare_results(metric,p, r, f):
    return '\t{}:\t{}: {:5.2f}\t{}: {:5.2f}\t{}: {:5.2f}'.format(metric, 'P', 100.0 * p, 'R', 100.0 * r, 'F1', 100.0 * f)

import random

def main():
  MAX_ARTICLE_LEN = 1024
  MAX_SUMMARY_LEN = 500
  BATCH_SIZE = 2
  TRAIN_EPOCHS = 10
  VALID_EPOCHS = 1
  TRAIN_BATCH_SIZE = 2
  VALID_BATCH_SIZE = 2
  MODEL_NAME = 'facebook/bart-base'
  LEARNING_RATE = 1e-4

  # Set random seeds and deterministic pytorch for reproducibility
  torch.manual_seed(RANDOM_SEED) # pytorch random seed
  np.random.seed(RANDOM_SEED) # numpy random seed
  torch.backends.cudnn.deterministic = True

  tokenizer = BartTokenizer.from_pretrained('facebook/bart-base')
  random_number = random.randint(0,1000)
  print(random_number)
  #df_val = df
  df_train, df_val = train_test_split(df, test_size=0.2, random_state=random_number,shuffle=True)
 

  df_train.reset_index(drop=True,inplace=True)
  df_val.reset_index(drop=True,inplace=True)
  
  df_train.to_excel('/content/gdrive/MyDrive/Colab Notebooks/data/ScisummNet_output/Results/trainingset.xlsx')
  df_val.to_excel('/content/gdrive/MyDrive/Colab Notebooks/data/ScisummNet_output/Results/validationset.xlsx')
  
  training_set = CustomDataset(df_train, tokenizer, MAX_ARTICLE_LEN, MAX_SUMMARY_LEN)
  val_set = CustomDataset(df_val, tokenizer, MAX_ARTICLE_LEN, MAX_SUMMARY_LEN)
  
  train_params = {
        'batch_size': TRAIN_BATCH_SIZE,
        'shuffle': True,
        'num_workers': 4
        }

  val_params = {
        'batch_size': VALID_BATCH_SIZE,
        'shuffle': False,
        'num_workers': 4
        }

    # Creation of Dataloaders for testing and validation. This will be used down for training and validation stage for the model.
  training_loader = DataLoader(training_set, **train_params)
  val_loader = DataLoader(val_set, **val_params)

  model = BartForConditionalGeneration.from_pretrained("/content/gdrive/MyDrive/Colab Notebooks/model/summarization_bart_model")
  model = model.to(device)

  optimizer = torch.optim.Adam(params =  model.parameters(), lr=LEARNING_RATE)

  print('Initiating Training for the model on our dataset')
  for epoch in range(TRAIN_EPOCHS):
    train(epoch, tokenizer, model, device, training_loader, optimizer)

  print('Now generating summaries on our trained model for the validation dataset and saving it in a dataframe')
  for epoch in range(VALID_EPOCHS):
    predictions, actuals = validate(epoch, tokenizer, model, device, val_loader)
    final_df = pd.DataFrame({'Generated Text':predictions,'Actual Text':actuals})
        #final_df.to_csv('./models/predictions.csv')
    final_df.to_excel('/content/gdrive/MyDrive/Colab Notebooks/data/ScisummNet_output/Results/predictions.xlsx')
    print('Output Files generated for review')

  for aggregator in ['Avg']:
    print('Evaluation with {}'.format(aggregator))
    apply_avg = aggregator == 'Avg'
    

    evaluator = rouge.Rouge(metrics=['rouge-n', 'rouge-l', 'rouge-w'],
                           max_n=4,
                           limit_length=False,
                           #length_limit=100,
                           #length_limit_type='words',
                           apply_avg=apply_avg,
                           alpha=0.5, # Default F1_score
                           weight_factor=1.2,
                           stemming=True)

    all_hypothesis = predictions
    all_references = actuals

    scores = evaluator.get_scores(all_hypothesis, all_references)

    for metric, results in sorted(scores.items(), key=lambda x: x[0]):
      if apply_avg: # value is a type of list as we evaluate each summary vs each reference
        print(prepare_results(metric,results['p'], results['r'], results['f']))


if __name__ == '__main__':
    main()

df_pred = pd.read_excel('/content/gdrive/MyDrive/Colab Notebooks/data/ScisummNet_output/Results/predictions.xlsx')
df_val = pd.read_excel('/content/gdrive/MyDrive/Colab Notebooks/data/ScisummNet_output/Results/validationset.xlsx')

df_pred.reset_index(drop=True,inplace=True)
df_val.reset_index(drop=True,inplace=True)

df_pred.head()

df_val.head()

df_pred['article_content'] = df_val['article_content_citations']

evaluator = rouge.Rouge(metrics=['rouge-n', 'rouge-l'],
                           max_n=2,
                           limit_length=False,
                           #length_limit=100,
                           #length_limit_type='words',
                           alpha=0.5, # Default F1_score
                           stemming=True)

rouge1r_list = list()
rouge1f_list = list()
rouge2r_list = list()
rouge2f_list = list()
rougelr_list = list()
rougelf_list = list()

for i in range(len(df_pred)):
  hypothesis = df_pred.loc[i,"Generated Text"]
  reference = df_pred.loc[i,"Actual Text"]
  scores = evaluator.get_scores(hypothesis, reference)
  print(scores)
  rouge1r = scores['rouge-1']['r']
  rouge1f = scores['rouge-1']['f']
  rouge2r = scores['rouge-2']['r']
  rouge2f = scores['rouge-2']['f']
  rougelr = scores['rouge-l']['r']
  rougelf = scores['rouge-l']['f']

  rouge1r_list.append(rouge1r)
  rouge1f_list.append(rouge1f)
  rouge2r_list.append(rouge2r)
  rouge2f_list.append(rouge2f)
  rougelr_list.append(rougelr)
  rougelf_list.append(rougelf)

df_pred['rouge-1-r'] = rouge1r_list
df_pred['rouge-1-f'] = rouge1f_list
df_pred['rouge-2-r'] = rouge2r_list
df_pred['rouge-2-f'] = rouge2f_list
df_pred['rouge-l-r'] = rougelr_list
df_pred['rouge-l-f'] = rougelf_list

df_pred.head()

df_pred.to_excel('/content/gdrive/MyDrive/Colab Notebooks/data/ScisummNet_output/Results/detailed_predictions.xlsx')

df_pred_rouge = df_pred[['rouge-2-f','rouge-l-f']]

lowest_rouge_index = df_pred_rouge.apply(lambda s: pd.Series(s.nsmallest(10).index))
largest_rouge_index = df_pred_rouge.apply(lambda s: pd.Series(s.nlargest(10).index))

lowest_rouge_index.head()

largest_rouge_index.head()

lowest_rouge_index.to_excel('/content/gdrive/MyDrive/Colab Notebooks/data/ScisummNet_output/Results/lowest_rouge.xlsx')

largest_rouge_index.to_excel('/content/gdrive/MyDrive/Colab Notebooks/data/ScisummNet_output/Results/largest_rouge.xlsx')