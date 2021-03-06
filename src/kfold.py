import os
from scipy.io import wavfile
import pandas as pd
import numpy as np
from keras.layers import Conv2D, MaxPool2D, Flatten
from keras.layers import Dropout, Dense
from keras.models import Sequential
from keras.utils import to_categorical
from sklearn.model_selection import KFold
from tqdm import tqdm
from python_speech_features import mfcc
import pickle
from keras.callbacks import ModelCheckpoint
from cfg4 import config
   
csv_namefile = 'effets_guitare4.csv'  
clean_namedir =  'clean4' 
config = config()


def Init (csv_namefile):
                
    # Téléchargement du fichier Excel qui contient le nom de la piste avec label qui le correspond       
    df = pd.read_csv(csv_namefile)
    df.set_index('fname', inplace=True)
    
    # Récuperer les échantions nettoyées et le calcul de la longeur de chaque piste
    for f in df.index:
        rate, signal = wavfile.read(clean_namedir+'/'+f)
        df.at[f, 'length'] = signal.shape[0]/rate
        
    # Récupérer les labelles des classes : Chorus , Nickel-Power , Reverb - Phaser_ 
    classes = list(np.unique(df.label))
    class_dist = df.groupby(['label'])['length'].mean()
    # Création des N sample , la probabilité de distribution 
    n_samples = 2* int(df['length'].sum()/0.1)
    prob_dist = class_dist / class_dist.sum()
    # choices = np.random.choice(class_dist.index, p=prob_dist)

    
    return df, classes , class_dist , n_samples , prob_dist

    
# Verifier si un modele existe déja pour éviter la répétition du travail 
def check_config():
    if os.path.isfile(config.p_path) :
        print('Loading existing data {} for model'.format(config.mode))
        with open(config.p_path,'rb') as handle:
            tmp = pickle.load(handle)
            return tmp
    else:
        return None

# Verifier si il existe déja  des échantillons préparées pour éviter la répétition du travail 
def check_samples():
    if os.path.isfile(config.samples_path) :
        print('Loading existing samples {} for model'.format(config.mode))
        with open(config.samples_path,'rb') as handle:
            samp = pickle.load(handle)
            return samp
    else:
        return None
# Verifier si il existe déja  des données préparées pour éviter la répétition du travail    
def check_Kfold():
    if os.path.isfile(config.kfold_path) :
        print('Loading existing kfold data {} for model '.format(config.mode))
        with open(config.kfold_path,'rb') as handle:
            kf = pickle.load(handle)
            return kf
    else:
        return None
    
# Creation des échantillons    
def build_rand_feat(csv_namefile,clean_namedir):
    
    #Initialiser les variables utilisées 
    df, classes , class_dist , n_samples , prob_dist = Init(csv_namefile)

    
    # tmp = check_config()
    # if tmp:
    #    return tmp.data[0], tmp.data[1]
    
    samp = check_samples()
    if samp :
        return samp[0], samp[1]
    
 
    #Pre-processing
    X=[]
    y=[]
    _min,_max = float('inf'), -float('inf')
    for _ in tqdm(range(n_samples)):
        rand_class= np.random.choice(class_dist.index,p=prob_dist)
        file = np.random.choice(df[df.label==rand_class].index)
        rate , wav= wavfile.read(clean_namedir+'/'+file)
        label = df.at[file,'label']
        rand_index=np.random.randint(0,wav.shape[0]-config.step )
        sample = wav[rand_index:rand_index+config.step]
        X_sample = mfcc(sample,rate,numcep=config.nfeat,nfilt=config.nfilt,
                       nfft = config.nfft )
        _min=min(np.amin(X_sample), _min)
        _max=max(np.amax(X_sample), _max)
        X.append(X_sample)
        y.append(classes.index(label))
        
    config.min = _min
    config.max = _max 
    X ,y = np.array(X), np.array(y)
    X = (X - _min) / (_max - _min)
    
    X = X.reshape(X.shape[0],X.shape[1],X.shape[2], 1)
    y = to_categorical(y,num_classes=4)
    
    config.data = (X , y)
    with open(config.p_path , 'wb') as handle:
        pickle.dump(config, handle, protocol=2)
        
    with open(config.samples_path , 'wb') as handle:
        pickle.dump(config.data, handle, protocol=2)    
        
    return X,y


# Modele convolutionnel
def get_conv_model(input_shape):
    model = Sequential()
    model.add(Conv2D(16,(3,3),activation='relu',strides=(1,1),
                     padding='same', input_shape=input_shape))
    model.add(Conv2D(32,(3,3),activation='relu',strides=(1,1),
                     padding='same'))
    model.add(Conv2D(64, (3,3),activation='relu',strides=(1,1),
                      padding='same'))
    model.add(Conv2D(128,(3,3),activation='relu',strides=(1,1),
                      padding='same'))
    model.add(Conv2D(256,(3,3),activation='relu',strides=(1,1),
                      padding='same'))
    
    
    model.add(MaxPool2D((2,2)))
    model.add(Dropout(0.5))
    model.add(Flatten())
    model.add(Dense(128,activation='relu'))
    model.add(Dense(64,activation='relu'))
    model.add(Dense(4,activation='softmax'))
    model.summary()
    
    model.compile(loss='categorical_crossentropy', 
                  optimizer='adam',
                  metrics=['acc'])
    return model


# KFOLD method
def get_score_KFOLD(model,X, y,nb_splits):
    
    
# Vérifier s'il existe des donnés déjà préparés par Kfold pour meme X et y et nb_splits
    kf = check_Kfold()
    if kf :
        if kf[1] == nb_splits and kf[2].all() == X.all() and kf[3].all() == y.all():
            return kf[0], kf[1]
    
    kf = KFold(n_splits = nb_splits)
    scors_CNN = []

    for train_index, test_index in kf.split(X):
        train_X , test_X , train_y ,test_y = X[train_index] , X[test_index],y[train_index],y[test_index]

        checkpoint = ModelCheckpoint(config.model_path, monitor='val_acc', verbose =1, mode ='max',
                         save_best_only=True, save_weights_only=False, period=1)
        model.fit(train_X,train_y,epochs=5,batch_size=32,validation_data =(test_X , test_y) ,
                  callbacks = [checkpoint])
        score =model.evaluate(test_X,test_y)
        scors_CNN.append(score)
        
    data =(scors_CNN , nb_splits , X , y)
    
    with open(config.kfold_path , 'wb') as handle:
        pickle.dump(data, handle, protocol=2)  
        
    return scors_CNN , nb_splits

 



# La phase d'apprentissage 
X , y = build_rand_feat(csv_namefile,clean_namedir)
input_shape = (X.shape[1],X.shape[2], 1 )
model = get_conv_model(input_shape)
Kfold , nb_splits  = get_score_KFOLD(model,X,y,5)



# Résultat acc et loss pour chaque itération(split =5)  + La moyenne de la précision 
print('Scores :============================')
for i in range(nb_splits):
    print('Split numéro  :')
    print(i)
    print('loss :')
    print(Kfold[i][0])
    print('acc :')
    print(Kfold[i][1])
    print('====================================')


somme = 0
for i in range(nb_splits):
    somme += Kfold[i][1]

Avg = somme /float(len(Kfold))
print('\nAverage score :' )
print(Avg *100)


model.save(config.model_path)






