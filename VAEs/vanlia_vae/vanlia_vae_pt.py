
# coding: utf-8

# 本实验打算实现一个最基本的vae，同时探讨以下几个问题：
# * 计算隐变量的期望与方差。
# * 把隐变量可视化。
# * 用指定 X 的隐变量 z 作为输入，查看生产的结果。
# * 用连续的隐变量作为输出，查看输出图像是否连续变化。

# In[3]:

# 引入相关包


# In[16]:

import os
import torch
import torch.nn as nn
from torch.autograd import Variable
from torchvision import datasets, transforms
# from fashion_datasets import fashion


# 一些全局变量

# In[5]:

batch_sz = 100
dim_img = 784
dim_z = 32
save_dir = 'out/vanila_vae/'
use_gpu = torch.cuda.is_available()


# 模型

# In[7]:

class VAE(nn.Module):
    def __init__(self):
        super(VAE, self).__init__()
        self.encoder_ = torch.nn.Sequential(
            torch.nn.Linear(dim_img, 256),
            torch.nn.ReLU(),
            torch.nn.Linear(256,64),
            torch.nn.Sigmoid(),
            torch.nn.Linear(64, 2*dim_z))
        self.decoder_ = torch.nn.Sequential(
            torch.nn.Linear(dim_z, 64),
            torch.nn.ReLU(),
            torch.nn.Linear(64,256),
            torch.nn.Softplus(),
            torch.nn.Linear(256, dim_img),
            torch.nn.Sigmoid())

    def encoder(self, x):
        out = self.encoder_(x)
        return out[:, 0:dim_z], out[:, dim_z:2 * dim_z]

    def decoder(self, z):
        return self.decoder_(z)

    def sample_z(self, mu, logvar):
        std = torch.exp(logvar * 0.5)
        eps = Variable(torch.randn(std.size()))
        if use_gpu:
            eps = eps.cuda()
        return mu + std * eps


    def forward(self, x):
        mu, logvar = self.encoder(x)
        z = self.sample_z(mu, logvar)
        return self.decoder(z), mu, logvar


# 训练相关对象声明

# In[8]:

model = VAE()
if use_gpu:
    model.cuda()

bce_criterion = nn.BCELoss(size_average=False)
solver = torch.optim.Adam(model.parameters())


# ~~导入Mnist手写体数据集。~~
# 导入fashion数据集

# In[18]:

train_datasets = datasets.MNIST('../datasets/mnist', train=True, download=True,
                               transform=transforms.Compose([transforms.ToTensor()]))
#normalize = transforms.Normalize(mean=[x / 255.0 for x in [125.3, 123.0, 113.9]],
#                                     std=[x / 255.0 for x in [63.0, 62.1, 66.7]])
#transform = transforms.Compose([transforms.ToTensor(),
#                                    transforms.Normalize((0.1307,), (0.3081,))])
#train_datasets = fashion(root='../datasets/fashion', train=True, transform=transform, download=True)
train_loader = torch.utils.data.DataLoader(
        dataset=train_datasets,
        batch_size=batch_sz, shuffle=True)


# 定义损失函数

# In[10]:

def loss_f(recon_x, x, mu, logvar):
    recon_loss = bce_criterion(recon_x, x)
    kld_element = mu.pow(2).add_(logvar.exp()).mul_(-1).add_(1).add_(logvar)
    kld_loss = torch.sum(kld_element).mul_(-0.5)

    return recon_loss + kld_loss


# 训练过程

# In[12]:

def train(epoch):
    train_loss = 0
    for batch_idx, (data, _) in enumerate(train_loader):
        imgs = Variable(data.view(batch_sz, dim_img))
        if use_gpu:
            imgs = imgs.cuda()
        
        solver.zero_grad()
        recon_x, mu, logvar = model(imgs)
        loss = loss_f(recon_x, imgs, mu, logvar)
        loss.backward()
        solver.step()
        train_loss += loss.data[0]

    print('====> Epoch: {} Average loss: {:.4f}'.format(
        epoch, train_loss / len(train_loader.dataset)))


if __name__ == '__main__':
    saved_model = 'vanlia_vae_pt.pkl'
    for e in range(250):
        train(e)
    torch.save(model.state_dict(), saved_model)