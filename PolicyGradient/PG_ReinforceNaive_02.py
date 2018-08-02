from collections import deque
from itertools import count

import torch.optim as optim

from atari_wrappers import get_env
from models import *

GAMMA = 0.99
LR = 0.0005

model_name = 'ReinforceNaive_02'
env_id = "PongNoFrameskip-v4"
identity = env_id + '_' + model_name
env = get_env(env_id)
net = AtariPolicyNet(env.observation_space.shape, env.action_space.n)


def calc_qvals(rewards):
    res = []
    sum_r = 0.0
    for r in reversed(rewards):
        sum_r *= GAMMA
        sum_r += r
        res.append(sum_r)
    return list(reversed(res))


def one_episode():
    rewards = []
    selected_logprobs = []

    state = env.reset()
    while True:
        action, log_prob = net.action_and_logprob(state)
        state, reward, is_done, _ = env.step(action)
        rewards.append(float(reward))
        selected_logprobs.append(log_prob)
        if is_done:
            break

    return rewards, selected_logprobs


# train
last_100_rewards = deque(maxlen=100)
trainer = optim.Adam(net.parameters(), lr=LR, betas=[0.5, 0.999])
for i_episode in count(1):
    loss = 0.0
    rewards, selected_logprobs = one_episode()
    qvals = calc_qvals(rewards)
    for qval, logprob in zip(qvals, selected_logprobs):
        loss -= qval * logprob
    trainer.zero_grad()
    loss.backward()
    trainer.step()

    last_100_rewards.append(sum(rewards))
    mean_reward = np.mean(last_100_rewards)
    if i_episode % 1 == 0:
        print('Episode: %d, loss: %.3f, mean_reward: %.3f' % (i_episode, loss.item(), mean_reward))

    # 停时条件
    if mean_reward >= 18:
        print("Solved!")
        torch.save(net.state_dict(), identity + '.pth')
        break
