import os

import torch
import torch.nn as nn
import torch.nn.functional as F

from torchvision.datasets import MNIST
import torchvision.transforms as tv_transforms
import torchvision.utils as tv_utils

import argparse

from models import Generator, Discriminator, ConditionalGenerator, ConditionalDiscriminator


################################################
# Parse parameters
################################################

parser = argparse.ArgumentParser()
parser.add_argument("--model_name", type=str, default='cgan', help="name of the model")
parser.add_argument("--data_root", type=str, default='../data', help="data folder")
parser.add_argument("--model_root", type=str, default='./models/', help="model folder")
parser.add_argument("--log_root", type=str, default=f'./logs/', help="log folder")
parser.add_argument("--figure_root", type=str, default=f'./figures/', help="log folder")
parser.add_argument("--seed", type=int, default=0, help="rng seed")
parser.add_argument("--image_size", type=int, default=32, help="image size of the inputs")
parser.add_argument("--batch_size", type=int, default=32, help="batch_size")
parser.add_argument("--gpu_id", type=str, default='0', help="gpu id assigned by cluster")
parser.add_argument("--n_workers", type=int, default=8, help="number of CPU workers for processing input data")
parser.add_argument("--learning_rate", type=float, dest='lr', default=0.0002, help="rng seed")
parser.add_argument("--epochs", type=int, dest='n_epochs', default=20, help="number of epochs")
parser.add_argument("--log_interval", type=int, dest='log_interval', default=100,  help="number of batches to record history")
parser.add_argument("--use_sn", dest='use_sn', default=False, action='store_true', help="use spectral normalization")

parser.add_argument("--conditional_G", dest='conditional_G', default=False, action='store_true', help="conditional generator")
parser.add_argument("--conditional_D", dest='conditional_D', default=False, action='store_true', help="conditional discriminator")
parser.add_argument("--include_c_in_z", dest='include_c_in_z', default=False, action='store_true', help="include conditioned variable ar part of noise vector")
args = parser.parse_args()

args.figure_root = os.path.join(args.figure_root, args.model_name)
args.model_root = os.path.join(args.model_root, args.model_name)

locals().update(vars(args))

dim_z = 50
beta1 = 0.5
num_classes = 10

################################################
# Prepare
################################################

os.makedirs(figure_root, exist_ok=True)

torch.manual_seed(seed)
if torch.cuda.is_available():
    torch.cuda.manual_seed(seed)

os.environ['CUDA_VISIBLE_DEVICES'] = gpu_id
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

train_loader = torch.utils.data.DataLoader(
    MNIST(
        root='./data', download=True, train=True, transform=tv_transforms.Compose([
            tv_transforms.Resize(image_size),
            tv_transforms.ToTensor(),
            tv_transforms.Normalize((0.5,), (0.5,)),
        ])),
    batch_size=batch_size, shuffle=True, num_workers=n_workers, pin_memory=True)

################################################
# model/loss/optimizer
################################################

conv_channels = [256, 256, 128, 64]
conv_upsample = [True, True, True]

conv_channels = [1, 64, 128, 256]
conv_dnsample = [True, True, True]

if conditional_G:
    G = ConditionalGenerator(conv_channels, conv_upsample, num_classes=10, dim_z=dim_z, im_channels=1).to(device)
else:
    G = Generator(conv_channels, conv_upsample, dim_z=dim_z, im_channels = 1).to(device)
    
if conditional_D:
    D = ConditionalDiscriminator(conv_channels, conv_dnsample, num_classes, use_sn=use_sn).to(device)
else:
    D = Discriminator(conv_channels, conv_dnsample, use_sn=use_sn).to(device)


criterion = nn.BCEWithLogitsLoss()

fixed_z = torch.randn(100, dim_z, device=device)
fixed_c = torch.arange(10).repeat(10).to(device)

if include_c_in_z:
    fixed_z[:, -10:] = F.one_hot(fixed_c, 10)

# label flipping helps with training G!
real_label = 0
fake_label = 1

optimizerD = torch.optim.Adam(D.parameters(), lr=lr, betas=(beta1, 0.999))
optimizerG = torch.optim.Adam(G.parameters(), lr=lr, betas=(beta1, 0.999))


################################################
# Training Loop
################################################
torch.autograd.set_detect_anomaly(True)

for epoch in range(n_epochs):

    for it, (x_real, c_real) in enumerate(train_loader):

        # batch_size for last batch might be different ...
        batch_size = x_real.size(0)
        real_labels = torch.full((batch_size, 1), real_label, device=device)
        fake_labels = torch.full((batch_size, 1), fake_label, device=device)

        ##############################################################
        # Update Discriminator: Maximize E[log(D(x))] + E[log(1 - D(G(z)))]
        ##############################################################

        D.zero_grad()

        # a minibatch of samples from data distribution
        x_real, c_real = x_real.to(device), c_real.to(device)

        y = D(x_real, c_real) if conditional_D else D(x_real)
        loss_D_real = criterion(y, real_labels)
        loss_D_real.backward()

        # a minibatch of samples from the model distribution
        z = torch.randn(batch_size, dim_z, device=device)
        c_fake = torch.empty(batch_size, dtype=torch.long).random_(0, num_classes).to(device)

        if include_c_in_z:
            z[:, -num_classes:] = F.one_hot(c_fake, num_classes)

        x_fake = G(z, c_fake) if conditional_G else G(z)
        # https://github.com/pytorch/examples/issues/116
        # If we do not detach, then, although x_fake is not needed for gradient update of D,
        #   as a consequence of backward pass which clears all the variables in the graph
        #   graph for G will not be available for gradient update of G
        # Also for performance considerations, detaching x_fake will prevent computing 
        #   gradients for parameters in G
        y = D(x_fake.detach(), c_fake) if conditional_D else D(x_fake.detach())
        loss_D_fake = criterion(y, fake_labels)
        loss_D_fake.backward()

        loss_D = loss_D_real + loss_D_fake

        optimizerD.step()

        ##############################################################
        # Update Generator: Minimize E[log(1 - D(G(z)))] => Maximize E[log(D(G(z))))]
        ##############################################################

        G.zero_grad()

        y = D(x_fake, c_fake) if conditional_D else D(x_fake)
        loss_G = criterion(y, real_labels)
        loss_G.backward()

        optimizerG.step()

        ##############################################################
        # write/print
        ##############################################################
        
        loss_D = loss_D.item()
        loss_G = loss_G.item()
        loss_total = loss_D + loss_G
        
        global_step = epoch*len(train_loader)+it
        
        if it % log_interval == log_interval-1:
            print(f'[{epoch+1}/{n_epochs}][{it+1}/{len(train_loader)}]'
                f'loss: {loss_total:.4}\t'
                f'loss_D: {loss_D:.4}\t'
                f'loss_G: {loss_G:.4}')
            x_fake = G(fixed_z, fixed_c) if conditional_G else G(fixed_z)
            tv_utils.save_image(x_fake.detach(),
                os.path.join(figure_root,
                    f'{model_name}_epoch={epoch}_it={it}.png'), nrow=10)