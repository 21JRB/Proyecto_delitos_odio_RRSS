# -*- coding: utf-8 -*-
"""version-3-distilbert.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1-8DIia6aa1Pp1j8u1SLnEAdBeMIoGpqm
"""

# This Python 3 environment comes with many helpful analytics libraries installed
# It is defined by the kaggle/python Docker image: https://github.com/kaggle/docker-python
# For example, here's several helpful packages to load

import numpy as np # linear algebra
import pandas as pd # data processing, CSV file I/O (e.g. pd.read_csv)

# Input data files are available in the read-only "../input/" directory
# For example, running this (by clicking run or pressing Shift+Enter) will list all files under the input directory

import os
for dirname, _, filenames in os.walk('/kaggle/input'):
    for filename in filenames:
        print(os.path.join(dirname, filename))

# You can write up to 20GB to the current directory (/kaggle/working/) that gets preserved as output when you create a version using "Save & Run All"
# You can also write temporary files to /kaggle/temp/, but they won't be saved outside of the current session

# Importación de las bibliotecas necesarias para el preprocesamiento de datos,
#entrenamiento del modelo, evaluación y clasificación de textos de prueba
import pandas as pd
import numpy as np

import torch
from torch.utils.data import DataLoader, RandomSampler, SequentialSampler, TensorDataset
from transformers import DistilBertTokenizer, DistilBertForSequenceClassification
from transformers import AdamW, get_linear_schedule_with_warmup

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.preprocessing import LabelEncoder


import time
import random
from tqdm.notebook import tqdm
import textwrap

import gradio as gr
import tensorflow as tf

from contextlib import redirect_stdout
import sys

import warnings

warnings.filterwarnings("ignore")

# Definición de las matrices
pd.set_option("display.max_columns", None)

#Cargar el dataset y definir el total de registros sobre los cuales iterar
df = pd.read_csv('fusionado.csv')
df = df[0:40000]

# Preprocesamiento de datos
le = LabelEncoder()
df['label'] = le.fit_transform(df['label'])

#División de datos de entrenamiento y prueba
X_train, X_val, y_train, y_val = train_test_split(df['text'], df['label'], test_size=0.15, random_state=17, stratify=df['label'])

print(X_train)

#Reemplazar valores de la columna text
train_indices = df['text'] == 'train'
df.loc[train_indices, 'text'] = 'train'

val_indices = df['text'] == 'val'
df.loc[val_indices, 'text'] = 'val'

#Transformación del texto en tokens
tokenizer = DistilBertTokenizer.from_pretrained('distilbert-base-uncased',
                                          do_lower_case = True)

#Tokenización del conjunto de entrenamiento
encoded_data_train = tokenizer.batch_encode_plus(
    X_train.tolist(),
    add_special_tokens=True,
    truncation=True,
    padding=True,
    max_length=150,
    return_attention_mask=True,
    return_tensors='pt'
)

#Tokenización del conjunto de validación
encoded_data_val = tokenizer.batch_encode_plus(
    X_val.tolist(),
    add_special_tokens=True,
    truncation=True,
    padding=True,
    max_length=150,
    return_attention_mask=True,
    return_tensors='pt'
)

#Codificación del conjunto de entrenamiento
input_ids_train = encoded_data_train['input_ids']
attention_masks_train = encoded_data_train['attention_mask']
labels_train = torch.tensor(y_train.values)

#Codificación el conjunto de validación
input_ids_val = encoded_data_val['input_ids']
attention_masks_val = encoded_data_val['attention_mask']
labels_val = torch.tensor(y_val.values)

# Creación del dataloader para train y val
dataset_train = TensorDataset(input_ids_train,
                              attention_masks_train,
                              labels_train)

dataset_val = TensorDataset(input_ids_val,
                             attention_masks_val,
                             labels_val)

batch_size = 64
dataloader_train = DataLoader(dataset_train, sampler=RandomSampler(dataset_train), batch_size=batch_size)
dataloader_val = DataLoader(dataset_val, sampler=SequentialSampler(dataset_val), batch_size=32)

# Carga del modelo pre-entrenado de DistilBERT
model = DistilBertForSequenceClassification.from_pretrained('distilbert-base-uncased',
                                                      num_labels = len(df.label.unique()),
                                                      output_attentions = False,
                                                      output_hidden_states = False)

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model.to(device)

#Definición del total de épocas
epochs = 5

#Configuración del optimizador y del programador de tasa de aprendizaje
optimizer = AdamW(model.parameters(),
                 lr = 1e-5,
                 eps = 1e-8) #2e-5 > 5e-5

#Cargar scheduler
scheduler = get_linear_schedule_with_warmup(optimizer,
                                           num_warmup_steps = 0,
                                           num_training_steps = len(dataloader_train)*epochs)

#Definición de funciones de evaluación
def accuracy_per_class(preds, labels):
    label_dict_inverse = {v: k for k, v in le.classes_.items()}
    preds_flat = np.argmax(preds, axis=1).flatten()
    labels_flat = labels.flatten()
    for label in np.unique(labels_flat):
        y_preds = preds_flat[labels_flat == label]
        y_true = labels_flat[labels_flat == label]
        print(f'Class: {label_dict_inverse[label]}')
        print(f'Accuracy: {len(y_preds[y_preds == label])}/{len(y_true)}\n')

def evaluate(dataloader_test):
    model.eval()
    loss_val_total = 0
    predictions, true_vals = [], []

    for batch in tqdm(dataloader_test):
        batch = tuple(b.to(device) for b in batch)
        inputs = {
            'input_ids': batch[0],
            'attention_mask': batch[1],
            'labels': batch[2]
        }

        with torch.no_grad():
            outputs = model(**inputs)

        loss = outputs.loss
        logits = outputs.logits
        loss_val_total += loss.item()

        logits = logits.detach().cpu().numpy()
        label_ids = inputs['labels'].cpu().numpy()
        predictions.extend(logits)
        true_vals.extend(label_ids)

    loss_val_avg = loss_val_total / len(dataloader_test)

    predictions = np.argmax(predictions, axis=1)

    return loss_val_avg, predictions, true_vals

#Configuración de la semilla aleatoria
seed_val = 17
random.seed(seed_val)
np.random.seed(seed_val)
torch.manual_seed(seed_val)
torch.cuda.manual_seed_all(seed_val)

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model.to(device)
print(device)

from transformers import DistilBertTokenizer, DistilBertForSequenceClassification
import torch
import textwrap
import sys
import gradio as gr
from itertools import product
import time
from tqdm import tqdm

# Definir lista de valores para los hiperparámetros a probar
learning_rates = [0.001, 0.01, 0.1]
batch_sizes = [16, 32, 64]
num_layers = [2, 4, 6]

# Función de entrenamiento y evaluación
def trainAndEvaluate(learning_rate, batch_size, num_layer):
    # Tu código de entrenamiento y evaluación aquí
    # ...

    # Entrenamiento del modelo
    for epoch in range(1, epochs+1):
        start_time = time.time()

        # set model in train mode
        model.train()

        # tracking variable
        loss_train_total = 0

        # set up progress bar
        progress_bar = tqdm(dataloader_train,
                            desc='Epoch {:1d}'.format(epoch),
                            leave=False,
                            disable=False)

        for batch in progress_bar:
            # set gradient to 0
            model.zero_grad()

            # load into GPU
            batch = tuple(b.to(device) for b in batch)

            # define inputs
            inputs = {'input_ids': batch[0],
                      'attention_mask': batch[1],
                      'labels': batch[2]}

            outputs = model(**inputs)
            loss = outputs[0] #output.loss
            loss_train_total += loss.item()

            # backward pass to get gradients
            loss.backward()

            # clip the norm of the gradients to 1.0 to prevent exploding gradients
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)

            # update optimizer
            optimizer.step()

            # update scheduler
            scheduler.step()

            progress_bar.set_postfix({'training_loss': '{:.3f}'.format(loss.item()/len(batch))})

        epoch_time = time.time() - start_time

        tqdm.write('\nEpoch {} de {}'.format(epoch, epochs))
        minutes = int(epoch_time // 60)
        seconds = int(epoch_time % 60)
        tqdm.write('Epoch Time: {} minutes {} seconds'.format(minutes, seconds))

        # print training result
        loss_train_avg = loss_train_total / len(dataloader_train)
        tqdm.write(f'Training loss: {loss_train_avg}')

        # evaluate
        val_loss, predictions, true_vals = evaluate(dataloader_val)
        # f1 score
        val_f1 = f1_score(predictions, true_vals)
        tqdm.write(f'Validation loss: {val_loss}')
        tqdm.write(f'F1 Score (weighted): {val_f1}')

# Crear todas las combinaciones posibles de hiperparámetros
hyperparameter_combinations = product(learning_rates, batch_sizes, num_layers)

# Realizar las pruebas para cada combinación de hiperparámetros
for learning_rate, batch_size, num_layer in hyperparameter_combinations:
    # Imprimir los hiperparámetros utilizados para esta prueba
    print(f"Prueba con learning_rate={learning_rate}, batch_size={batch_size}, num_layer={num_layer}")

    # Llamar a la función de entrenamiento y evaluación con los hiperparámetros específicos
    trainAndEvaluate(learning_rate, batch_size, num_layer)
    print("----------------------------------------------")

# Interfaz de usuario de Gradio
iface = gr.Interface(fn=trainAndEvaluate, inputs=["text", gr.inputs.Slider(1, 512, 1, default=150)], outputs="text")
iface.launch()

#Guardado del modelo
model.save_pretrained("modelDtBert.h5")

from transformers import DistilBertTokenizer, DistilBertForSequenceClassification
import torch
import textwrap
import sys
import gradio as gr
from itertools import product

# Definir lista de valores para los hiperparámetros a probar
learning_rates = [0.001, 0.01, 0.1]
batch_sizes = [16, 32, 64]
num_layers = [2, 4, 6]

# Función de clasificación de sentimientos con hiperparámetros ajustables
def classifySentiment(text, learning_rate, batch_size, num_layer):
    tokenizer = DistilBertTokenizer.from_pretrained('distilbert-base-uncased', do_lower_case=True)
    model = DistilBertForSequenceClassification.from_pretrained('distilbert-base-uncased', num_labels=2)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model.to(device)

    encoded_text = tokenizer.encode_plus(
        text,
        max_length=150,
        truncation=True,
        add_special_tokens=True,
        return_token_type_ids=False,
        pad_to_max_length=True,
        return_attention_mask=True,
        return_tensors='pt'
    )

    input_ids = encoded_text['input_ids'].to(device)
    attention_mask = encoded_text['attention_mask'].to(device)

    model.eval()
    with torch.no_grad(), redirect_stdout(sys.stdout):
        inputs = {'input_ids': input_ids, 'attention_mask': attention_mask}
        inputs = {key: value.to(device) for key, value in inputs.items()}
        output = model(**inputs)
        _, prediction = torch.max(output.logits, dim=1)

    print("\n".join(textwrap.wrap(text)))
    if prediction.item() == 1:
        print('Sentimiento predicho: * * * * *')
        return 'Sentimiento predicho: * * * * *'
    else:
        print('Sentimiento predicho: *')
        return 'Sentimiento predicho: *'

# Crear todas las combinaciones posibles de hiperparámetros
hyperparameter_combinations = product(learning_rates, batch_sizes, num_layers)

# Lista para almacenar los resultados de cada prueba
results = []

# Realizar las pruebas para cada combinación de hiperparámetros
for learning_rate, batch_size, num_layer in hyperparameter_combinations:
    result = classifySentiment(text, learning_rate, batch_size, num_layer)
    results.append(result)

# Imprimir los resultados de todas las pruebas
for i, result in enumerate(results):
    print(f"Resultados de prueba {i+1}: {result}")

# Interfaz de usuario de Gradio
iface = gr.Interface(fn=classifySentiment, inputs="text", outputs="text")
iface.launch()