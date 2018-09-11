import torch
import torch.nn as nn
from src.loss_func import NegativeSampling


class Context2vec(nn.Module):

    def __init__(self,
                 vocab_size,
                 counter,
                 word_embed_size,
                 hidden_size,
                 n_layers,
                 bidirectional,
                 dropout,
                 pad_index,
                 inference):

        super(Context2vec, self).__init__()
        self.vocab_size = vocab_size
        self.hidden_size = hidden_size
        self.n_layers = n_layers
        self.rnn_output_size = hidden_size
        self.weighting = True

        self.drop = nn.Dropout(dropout)
        self.l2r_emb = nn.Embedding(num_embeddings=vocab_size,
                                    embedding_dim=word_embed_size,
                                    padding_idx=pad_index)
        self.l2r_rnn = nn.LSTM(input_size=word_embed_size,
                               hidden_size=hidden_size,
                               num_layers=n_layers,
                               batch_first=True)
        self.r2l_emb = nn.Embedding(num_embeddings=vocab_size,
                                    embedding_dim=word_embed_size,
                                    padding_idx=pad_index)
        self.r2l_rnn = nn.LSTM(input_size=word_embed_size,
                               hidden_size=hidden_size,
                               num_layers=n_layers,
                               batch_first=True)
        self.criterion = NegativeSampling(word_embed_size,
                                          counter,
                                          ignore_index=pad_index,
                                          n_negatives=10,
                                          power=0.75)

        if self.weighting:
            self.weights = nn.Parameter(torch.zeros(2, hidden_size))
            self.gamma = nn.Parameter(torch.ones(1))
        else:
            self.MLP = MLP(input_size=hidden_size*2,
                           mid_size=hidden_size*2,
                           output_size=hidden_size,
                           dropout=dropout)

        self.init_weights()

    def init_weights(self):
        initrange = 0.1
        self.r2l_emb.weight.data.uniform_(-initrange, initrange)
        self.l2r_emb.weight.data.uniform_(-initrange, initrange)

    def forward(self,
                sentences,
                reversed_sentences,
                lengths):

        batch_size, seq_len = sentences.size()
        hidden = self.init_hidden(batch_size)

        l2r_emb = self.l2r_emb(sentences)
        r2l_emb = self.r2l_emb(reversed_sentences)

        packed_l2r_emb = l2r_emb
        packed_r2l_emb = r2l_emb
        if lengths is not None:
            lengths = lengths.view(-1).tolist()
            packed_l2r_emb = nn.utils.rnn.pack_padded_sequence(l2r_emb, lengths, batch_first=True)
            packed_r2l_emb = nn.utils.rnn.pack_padded_sequence(r2l_emb, lengths, batch_first=True)

        output_l2r, hidden = self.l2r_rnn(packed_l2r_emb)
        output_r2l, hidden = self.r2l_rnn(packed_r2l_emb)

        if lengths is not None:
            output_l2r = torch.nn.utils.rnn.pad_packed_sequence(output_l2r)[0]
            output_r2l = torch.nn.utils.rnn.pad_packed_sequence(output_r2l)[0]

        if self.weighting:
            s_task = torch.nn.functional.softmax(self.weights, dim=0)
            c_i = torch.stack((output_l2r, output_r2l), dim=2) * s_task
            c_i = self.gamma * c_i.sum(2)
        else:
            c_i = self.MLP(torch.cat((output_l2r, output_r2l), dim=2))

        print(c_i)
        quit()
        return 0

    def init_hidden(self, batch_size):
        weight = next(self.parameters())
        return (weight.new_zeros(self.n_layers, batch_size, self.hidden_size),
                weight.new_zeros(self.n_layers, batch_size, self.hidden_size))


class MLP(nn.Module):

    def __init__(self,
                 input_size,
                 mid_size,
                 output_size,
                 n_layers=2,
                 dropout=0.3,
                 activation_function='relu'):
        super(MLP, self).__init__()

        self.input_size = input_size
        self.mid_size = mid_size
        self.output_size = output_size
        self.n_layers = n_layers
        self.drop = nn.Dropout(dropout)

        self.MLP = nn.ModuleList()
        if n_layers == 1:
            self.MLP.append(nn.Linear(input_size, output_size))
        else:
            self.MLP.append(nn.Linear(input_size, mid_size))
            for _ in range(n_layers - 2):
                self.MLP.append(nn.Linear(mid_size, mid_size))
            self.MLP.append(nn.Linear(mid_size, output_size))

        if activation_function == 'tanh':
            self.activation_function = nn.Tanh()
        elif activation_function == 'relu':
            self.activation_function = nn.ReLU()
        else:
            raise NotImplementedError

    def forward(self, x):
        out = x
        for i in range(self.n_layers-1):
            out = self.MLP[i](self.drop(out))
            out = self.activation_function(out)
        return self.MLP[-1](self.drop(out))