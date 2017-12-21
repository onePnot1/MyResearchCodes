from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from collections import namedtuple

import tensorflow as tf

import utils.Utils as U

# GraphKeys 官方的都是大写命名，小写的命名不会冲突
TRAIN_INPUT_NAME = 'train_inputs_'
EMBEDDING_NAME = 'embedding_'
RNN_CELL_NAME = 'rnn_cell_'
PHASE_NAME = 'phase_'



class Hybird_CVAE(object):
    def __init__(self, flags):
        self.flags = flags
        self._build_graph()

    def _build_graph(self):
        self._init_once()
        self._build_train_graph()

        # self._build_sample_graph()
        # todo
        self.summary_op = tf.summary.merge_all()

    @U.run_once
    def _init_once(self):
        self._train_input_layer_init()
        self._embedding_layer_init()
        self._decoder_rnn_cell_init()
        tf.add_to_collection(PHASE_NAME, tf.placeholder(dtype=tf.bool, name='phase'))

    def _get_phase(self):
        return tf.get_collection(PHASE_NAME)[0]


    def _build_train_graph(self):
        inputs_ = self._get_train_inputs()

        mu, log_var = self._cnn_encoder_subgraph('cnn_encoder', inputs_.X, reuse=False)
        self.kld_loss = self._kld_loss(mu, log_var, 'kld_loss')
        z = self._sample_z_layer(mu, log_var, 'sample_z')
        vocab_logits = self._cnn_decoder_subgraph(z, 'cnn_decoder', reuse=False)
        self.aux_loss = self._aux_loss(vocab_logits, inputs_.X, 'aux_loss')
        rnn_logits = self._rnn_train_layer(vocab_logits, inputs_.Y_i, inputs_.Y_lengths, name='rnn_train')
        self.rec_loss = self._rec_loss(rnn_logits, inputs_.Y_t, inputs_.Y_mask, 'rec_loss')
        self.train_loss = self._train_loss(self.kld_loss, self.rec_loss, self.aux_loss, name='train_loss')
        self.train_op = self._train_op(self.train_loss)

    def _build_sample_graph(self):
        aux_loss, logits = self._cnn_decoder_subgraph('forward_z_subgraph', self.sample_input, reuse=True)
        # todo
        # next_symbol = tf.stop_gradient(tf.argmax(logits, 1))
        # next_input = tf.nn.embedding_lookup(self.embedding, next_symbol)

    def _cnn_encoder_subgraph(self, name, encoder_input, reuse=False):
        with tf.variable_scope(name, reuse=reuse):
            embedded_encoder_input = tf.nn.embedding_lookup(self._get_embedding(), encoder_input)
            encoder_cnn_output = self._encoder_conv_layer(embedded_encoder_input, 'encoder_layers')
            mu = tf.layers.dense(encoder_cnn_output, name='dense_mu', units=self.flags.z_size)
            log_var = tf.layers.dense(encoder_cnn_output, name='dense_log_var', units=self.flags.z_size)
        return mu, log_var

    def _cnn_decoder_subgraph(self, z, name, reuse=False):
        with tf.variable_scope(name, reuse=reuse):
            dconv_in = tf.layers.dense(z, 256 * int(self.flags.seq_len / 4), name='dense_dconv_input')
            dconv_out = self._decoder_dconv_layer(dconv_in, name='decoder_dconv_layer')
            vocab_logits = tf.layers.dense(dconv_out, self.flags.vocab_size, name='dc2vocab')

        return vocab_logits

    def _rnn_train_layer(self, vocab_logits, inputs, lengths, name):
        with tf.name_scope(name=name):
            embed_word_inputs = tf.nn.embedding_lookup(self._get_embedding(), inputs)
            rnn_cated_inputs = tf.concat([embed_word_inputs, vocab_logits], axis=-1)
            rnn_hidden_input = tf.layers.dense(rnn_cated_inputs, self.flags.rnn_hidden_size, name='rnn_input')
            rnn_hidden_output, _ = tf.nn.dynamic_rnn(self._get_rnn_cell(), rnn_hidden_input, lengths, dtype=tf.float32)
            rnn_logits = tf.layers.dense(rnn_hidden_output, self.flags.vocab_size, name='rnn_output')
        return rnn_logits

    def _train_op(self, loss):
        with tf.name_scope('train_op'):
            # for batch_normal to work correct
            update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
            with tf.control_dependencies(update_ops):
                t_vars = tf.trainable_variables()
                grads, _ = tf.clip_by_global_norm(tf.gradients(loss, t_vars), 5)
                optimizer = tf.train.AdamOptimizer(learning_rate=0.001)
                train_op = optimizer.apply_gradients(zip(grads, t_vars),
                                                     global_step=tf.train.get_or_create_global_step())
        return train_op

    def _embedding_layer_init(self):
        with tf.name_scope('embedding'):
            with tf.variable_scope('embedding', reuse=False):
                embedding = tf.get_variable(name='embedding',
                                            shape=[self.flags.vocab_size, self.flags.embed_size],
                                            dtype=tf.float32,
                                            initializer=tf.random_normal_initializer(stddev=0.1))
        tf.add_to_collection(EMBEDDING_NAME,embedding)

    def _get_embedding(self):
        return tf.get_collection(EMBEDDING_NAME)[0]

    def _train_input_layer_init(self):
        with tf.name_scope('TrainInputs'):
            tf.add_to_collection(TRAIN_INPUT_NAME,
                tf.placeholder(tf.int32, shape=[self.flags.batch_size, self.flags.seq_len], name='X'))
            tf.add_to_collection(TRAIN_INPUT_NAME,
                tf.placeholder(tf.int32, shape=[self.flags.batch_size, self.flags.seq_len], name='Y_i'))
            tf.add_to_collection(TRAIN_INPUT_NAME,
                tf.placeholder(tf.int32, shape=[self.flags.batch_size], name='Y_lengths'))
            tf.add_to_collection(TRAIN_INPUT_NAME,
                tf.placeholder(tf.int32, shape=[self.flags.batch_size, self.flags.seq_len], name='Y_t'))
            tf.add_to_collection(TRAIN_INPUT_NAME,
                tf.placeholder(tf.int32, shape=[self.flags.batch_size, self.flags.seq_len], name='Y_mask'))

    def _get_train_inputs(self):
        input_ = tf.get_collection(TRAIN_INPUT_NAME)
        TrainInputs = namedtuple('TrainInputs', ['X', 'Y_i', 'Y_lengths', 'Y_t', 'Y_mask'])
        return TrainInputs(input_[0], input_[1], input_[2], input_[3], input_[4])

    def _sample_input_layer(self, name):
        with tf.name_scope(name):
            sample_input = tf.placeholder(tf.float32,
                                          shape=[1, self.flags.z_size],
                                          name='sample_input_z')
        return sample_input

    def _encoder_conv_layer(self, input_embed, name):
        with tf.name_scope(name):
            cl1_output = self._encoder_conv1d_layer('encoder_conv_layer_1', input_embed,
                                                    filter_shape=(3, self.flags.embed_size, 128),
                                                    stride=2, padding='SAME')
            assert cl1_output.shape == (self.flags.batch_size, int(self.flags.seq_len / 2), 128)
            cl2_output = self._encoder_conv1d_layer('encoder_conv_layer_2', cl1_output,
                                                    filter_shape=(3, 128, 256),
                                                    stride=2, padding='SAME')
            assert cl2_output.shape == (self.flags.batch_size, int(self.flags.seq_len / 4), 256)
            encoder_cnn_output = tf.reshape(cl2_output,
                                            shape=[self.flags.batch_size,
                                                   256 * int(self.flags.seq_len / 4)],
                                            name='encoder_cnn_output')
        return encoder_cnn_output

    def _sample_z_layer(self, mu, log_var, name):
        with tf.name_scope(name):
            eps = tf.truncated_normal((self.flags.batch_size, self.flags.z_size), stddev=1.0)
            z = mu + tf.exp(0.5 * log_var) * eps

            tf.summary.histogram('z', z)
        return z

    def _decoder_dconv_layer(self, dc_input, name):
        with tf.name_scope(name):
            dc_input_ = tf.reshape(dc_input, [self.flags.batch_size, 1, int(self.flags.seq_len / 4), 256],
                                   name='in_shape')
            dct1_out = self._decoder_conv2d_transpose_layer(input=dc_input_,
                                                            filter_shape=[1, 3, 128, 256],
                                                            out_shape=[self.flags.batch_size, 1,
                                                                       int(self.flags.seq_len / 2), 128],
                                                            stride=[1, 1, 2, 1],
                                                            padding='SAME',
                                                            name='dct1')
            dct2_out = self._decoder_conv2d_transpose_layer(input=dct1_out,
                                                            filter_shape=[1, 3, 200, 128],
                                                            out_shape=[self.flags.batch_size, 1,
                                                                       self.flags.seq_len, 200],
                                                            stride=[1, 1, 2, 1],
                                                            padding='SAME',
                                                            name='dct2')

            decoder_cnn_output = tf.reshape(dct2_out, [self.flags.batch_size, self.flags.seq_len, 200])
        return decoder_cnn_output

    def _train_loss(self, kld_loss, rec_loss, aux_loss, name):
        with tf.name_scope(name):
            train_loss = kld_loss + rec_loss + aux_loss
        return train_loss

    @staticmethod
    def _kld_loss(mu, log_var, name):
        with tf.name_scope(name):
            kld_loss = tf.reduce_mean(-0.5 * tf.reduce_sum(log_var - tf.square(mu) - tf.exp(log_var) + 1, axis=1))
        return kld_loss

    @staticmethod
    def _rec_loss(logits, targets, masks, name):
        with tf.name_scope(name):
            rec_loss = tf.nn.sparse_softmax_cross_entropy_with_logits(logits=logits, labels=targets)
            rec_loss = tf.reduce_mean(tf.reduce_sum(rec_loss * tf.cast(masks, tf.float32), axis=1))
        return rec_loss

    @staticmethod
    def _aux_loss(logits, targets, name):
        with tf.name_scope(name):
            aux_loss = tf.nn.sparse_softmax_cross_entropy_with_logits(logits=logits, labels=targets)
            aux_loss = tf.reduce_mean(tf.reduce_sum(aux_loss, axis=1))
        return aux_loss

    def _encoder_conv1d_layer(self, name, input, filter_shape, stride=1, padding='SAME'):
        with tf.name_scope(name):
            with tf.variable_scope(name):
                filter = tf.get_variable(name='filter',
                                         shape=filter_shape,
                                         dtype=tf.float32,
                                         initializer=tf.random_normal_initializer(stddev=0.1))

                conv1d = tf.nn.conv1d(input, filter, stride, padding, name='conv1d')
                res = tf.nn.relu(tf.layers.batch_normalization(conv1d, training=self._get_phase()), name='relu')
        return res

    def _decoder_conv2d_transpose_layer(self, name, input, filter_shape, out_shape, stride, padding='SAME'):
        with tf.name_scope(name):
            with tf.variable_scope(name):
                filter = tf.get_variable(name='filter',
                                         shape=filter_shape,
                                         dtype=tf.float32,
                                         initializer=tf.random_normal_initializer(stddev=0.1))
                conv1d_transpose = tf.nn.conv2d_transpose(input, filter, out_shape, stride, padding,
                                                          name='conv2d_transpose')
                res = tf.nn.relu(tf.layers.batch_normalization(conv1d_transpose, training=self._get_phase()), name='relu')
        return res

    def _decoder_rnn_cell_init(self):
        with tf.name_scope('decoder_rnn_cell'):
            cell = tf.nn.rnn_cell.BasicLSTMCell(self.flags.rnn_hidden_size, reuse=False)
            cell = tf.nn.rnn_cell.DropoutWrapper(cell, input_keep_prob=0.8, output_keep_prob=0.8)
            cell = tf.nn.rnn_cell.MultiRNNCell([cell] * 2)
        tf.add_to_collection(RNN_CELL_NAME,cell)

    def _get_rnn_cell(self):
        return tf.get_collection(RNN_CELL_NAME)[0]

    def fit(self):
        None

    def infer(self):
        None
