# -- coding: utf-8 --

from __future__ import division
from __future__ import print_function
from model.hyparameter import parameter
from model.encoder import Encoderlstm
from model.decoder import Dcoderlstm
from model.utils import construct_feed_dict

import pandas as pd
import tensorflow as tf
import numpy as np
import matplotlib.pyplot as plt

import model.process as data_load
import os
import argparse
import shutil

tf.reset_default_graph()
os.environ["KMP_DUPLICATE_LIB_OK"]="TRUE"
logs_path="board"

class Model(object):
    def __init__(self,para):
        self.para=para
        self.pollutant_id={'AQI':3, 'PM2.5':4,'PM10':5, 'SO2':6, 'NO2':7, 'O3':8, 'CO':9}

        # define placeholders
        self.placeholders = {
            # None : batch _size * time _size
            'features': tf.placeholder(tf.float32, shape=[None, self.para.input_length, self.para.features]),
            'labels': tf.placeholder(tf.float32, shape=[None, self.para.output_length]),
            'dropout': tf.placeholder_with_default(0., shape=())
        }
        self.model()

    def model(self):
        '''
        :param batch_size: 64
        :param encoder_layer:
        :param decoder_layer:
        :param encoder_nodes:
        :param prediction_size:
        :param is_training: True
        :return:
        '''

        # create model

        # this step use to encoding the input series data
        '''
        rlstm, return --- for example ,output shape is :(32, 3,  128)
        axis=0: bath size
        axis=1: input data time size
        axis=2: output feature size
        '''
        encoder_init =Encoderlstm(self.para.batch_size,
                                    self.para.hidden_layer,
                                    self.para.hidden_size,
                                    placeholders=self.placeholders)

        ## [batch, time ,h]
        (h_states, c_states) = encoder_init.encoding(self.placeholders['features'])

        print('h_states shape is : ', h_states.shape)

        # encoder_init=encoder_lstm.lstm(self.para.batch_size,
        #                                self.para.hidden_layer,
        #                                self.para.hidden_size,
        #                                self.para.is_training)
        # encoder_init=encodet_gru.gru(self.x_input,batch_size,encoder_layer,encoder_nodes,is_training)
        # encoder_init=encoder_rnn.rnn(self.x_input,batch_size,encoder_layer,encoder_nodes,is_training)
        # (h_states,c_states)=encoder_init.encoding()

        # this step to presict the polutant concentration
        '''
        decoder, return --- for example ,output shape is :(32, 162, 1)
        axis=0: bath size
        axis=1: numbers of the nodes
        axis=2: label size
        '''
        decoder_init = Dcoderlstm(self.para.batch_size,
                                    self.para.output_length,
                                    self.para.hidden_layer,
                                    self.para.hidden_size,
                                    placeholders=self.placeholders)

        self.pres = decoder_init.decoding(h_states)
        print('pres shape is : ', self.pres.shape)

        self.cross_entropy = tf.reduce_mean(
            tf.sqrt(tf.reduce_mean(tf.square(self.pres + 1e-10 - self.placeholders['labels']), axis=0)))

        print(self.cross_entropy)
        print('cross shape is : ',self.cross_entropy.shape)

        tf.summary.scalar('cross_entropy',self.cross_entropy)
        # backprocess and update the parameters
        self.train_op = tf.train.AdamOptimizer(self.para.learning_rate).minimize(self.cross_entropy)

        print('#...............................in the training step.....................................#')

    def test(self):
        '''
        :param batch_size: usually use 1
        :param encoder_layer:
        :param decoder_layer:
        :param encoder_nodes:
        :param prediction_size:
        :param is_training: False
        :return:
        '''
        model_file = tf.train.latest_checkpoint('weights/')
        self.saver.restore(self.sess, model_file)

    def accuracy(self,label,predict):
        '''
        :param label: represents the observed value
        :param predict: represents the predicted value
        :param epoch:
        :param steps:
        :return:
        '''
        error = label - predict
        average_error = np.mean(np.fabs(error.astype(float)))
        print("mae is : %.6f" % (average_error))

        rmse_error = np.sqrt(np.mean(np.square(label - predict)))
        print("rmse is : %.6f" % (rmse_error))

        cor = np.mean(np.multiply((label - np.mean(label)),
                                  (predict - np.mean(predict)))) / (np.std(predict) * np.std(label))
        print('correlation coefficient is: %.6f' % (cor))

        # mask = label != 0
        # mape =np.mean(np.fabs((label[mask] - predict[mask]) / label[mask]))*100.0
        # mape=np.mean(np.fabs((label - predict) / label)) * 100.0
        # print('mape is: %.6f %' % (mape))
        sse = np.sum((label - predict) ** 2)
        sst = np.sum((label - np.mean(label)) ** 2)
        R2 = 1 - sse / sst  # r2_score(y_actual, y_predicted, multioutput='raw_values')
        print('r^2 is: %.6f' % (R2))

        return average_error,rmse_error,cor,R2

    def describe(self,label,predict,prediction_size):
        '''
        :param label:
        :param predict:
        :param prediction_size:
        :return:
        '''
        plt.figure()
        # Label is observed value,Blue
        plt.plot(label, 'b*:', label=u'actual value')
        # Predict is predicted value，Red
        plt.plot(predict, 'r*:', label=u'predicted value')
        # use the legend
        # plt.legend()
        plt.xlabel("time(hours)", fontsize=17)
        plt.ylabel("pm$_{2.5}$ (ug/m$^3$)", fontsize=17)
        plt.title("the prediction of pm$_{2.5}", fontsize=17)
        plt.show()

    def initialize_session(self):
        self.sess=tf.Session()
        self.saver=tf.train.Saver(var_list=tf.trainable_variables())

    def re_current(self, a, max, min):
        return [num*(max-min)+min for num in a]

    def run_epoch(self):
        '''
        from now on,the model begin to training, until the epoch to 100
        '''

        max_rmse = 100
        self.sess.run(tf.global_variables_initializer())
        merged = tf.summary.merge_all()
        writer = tf.summary.FileWriter(logs_path,graph=tf.get_default_graph())

        self.iterate = data_load.DataIterator(site_id=self.para.target_site_id,
                                              pollutant_id=self.pollutant_id[self.para.pollutant_id],
                                                is_training=self.para.is_training,
                                                time_size=self.para.input_length,
                                                prediction_size=self.para.output_length,
                                                data_divide=self.para.data_divide,
                                                window_step=self.para.step,
                                                normalize=self.para.normalize)

        next_elements=self.iterate.next_batch(batch_size=self.para.batch_size, epochs=self.para.epochs,is_training=True)

        for i in range(int((self.iterate.train_data.shape[0] - (self.para.input_length + self.para.output_length))//self.para.step)
                    // self.para.batch_size * self.para.epochs):

            x, label =self.sess.run(next_elements)
            feed_dict = construct_feed_dict(x, label, self.placeholders)
            feed_dict.update({self.placeholders['dropout']: self.para.dropout})

            summary, loss, _ = self.sess.run((merged,self.cross_entropy,self.train_op), feed_dict=feed_dict)
            print("after %d steps,the training average loss value is : %.6f" % (i, loss))
            # writer.add_summary(summary, loss)

            # if max_rmse > rmse_error:
            #     print("the validate average rmse loss value is : %.6f" % (rmse_error))
            #     max_rmse = rmse_error
            #     self.saver.save(self.sess, save_path=self.para.save_path + 'model.ckpt')

            # validate processing
            if i % 50 == 0:
                rmse_error=self.evaluate()

                if max_rmse>rmse_error:
                    print("the validate average rmse loss value is : %.6f" % (rmse_error))
                    max_rmse=rmse_error
                    self.saver.save(self.sess,save_path=self.para.save_path+'model.ckpt')

                    if os.path.exists('model1'):shutil.rmtree('model1')
                    builder = tf.saved_model.builder.SavedModelBuilder('model1')
                    builder.add_meta_graph_and_variables(self.sess, ["mytag"])
                    builder.save()

    def evaluate(self):
        '''
        :param para:
        :param pre_model:
        :return:
        '''
        label_list = list()
        predict_list = list()

        #with tf.Session() as sess:
        model_file = tf.train.latest_checkpoint(self.para.save_path)
        if not self.para.is_training:
            print('the model weights has been loaded:')
            self.saver.restore(self.sess, model_file)

        self.iterate_test = data_load.DataIterator(site_id=self.para.target_site_id,
                                                    pollutant_id=self.pollutant_id[self.para.pollutant_id],
                                                    is_training=self.para.is_training,
                                                    time_size=self.para.input_length,
                                                    prediction_size=self.para.output_length,
                                                    data_divide=self.para.data_divide,
                                                    normalize=self.para.normalize)

        next_ = self.iterate_test.next_batch(batch_size=self.para.batch_size, epochs=1,is_training=False)
        max,min=self.iterate_test.max_list[self.pollutant_id[self.para.pollutant_id]],self.iterate_test.min_list[self.pollutant_id[self.para.pollutant_id]]

        for i in range(int((self.iterate_test.test_data.shape[0] -(self.para.input_length+ self.para.output_length))//self.para.output_length)
                       // self.para.batch_size):
            x, label =self.sess.run(next_)
            feed_dict = construct_feed_dict(x, label, self.placeholders)
            feed_dict.update({self.placeholders['dropout']: 0.0})

            pre = self.sess.run((self.pres), feed_dict=feed_dict)
            label_list.append(label)
            predict_list.append(pre)

        label_list=np.reshape(np.array(label_list,dtype=np.float32),[-1, self.para.output_length])
        predict_list=np.reshape(np.array(predict_list,dtype=np.float32),[-1, self.para.output_length])

        if self.para.normalize:
            label_list = np.array([self.re_current(row,max,min) for row in label_list])
            predict_list = np.array([self.re_current(row,max,min) for row in predict_list])
        else:
            label_list = np.array([row for row in label_list])
            predict_list = np.array([row for row in predict_list])

        label_list=np.reshape(label_list,[-1])
        predict_list=np.reshape(predict_list,[-1])
        average_error, rmse_error, cor, R2= self.accuracy(label_list, predict_list)  #产生预测指标
        #pre_model.describe(label_list, predict_list, pre_model.para.prediction_size)   #预测值可视化
        return rmse_error

def main(argv=None):
    '''
    :param argv:
    :return:
    '''
    print('#......................................beginning........................................#')
    para = parameter(argparse.ArgumentParser())
    para = para.get_para()

    print('Please input a number : 1 or 0. (1 and 0 represents the training or testing, respectively).')
    val = input('please input the number : ')

    if int(val) == 1:para.is_training = True
    else:
        para.batch_size=1
        para.is_training = False

    pre_model = Model(para)
    pre_model.initialize_session()

    if int(val) == 1:pre_model.run_epoch()
    else:
        pre_model.evaluate()

    print('#...................................finished............................................#')

if __name__ == '__main__':
    main()