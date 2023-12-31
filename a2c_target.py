import numpy as np
import torch
import gym
import pygame
import collections
import random
import torch.nn.functional as F
from tqdm import tqdm
import matplotlib.pyplot as plt
import time
import torch.nn as nn
from rl_utils import plot_smooth_reward


class CriticNet(nn.Module):
    def __init__(self, state_dim, hidden_dim, action_dim) -> None:
        super().__init__()
        self.fc1 = torch.nn.Linear(state_dim, hidden_dim)
        self.fc2 = torch.nn.Linear(hidden_dim, 1)

    def forward(self, state):
        hidden_state = F.relu(self.fc1(state))
        acion_value = self.fc2(hidden_state)
        return acion_value


class ActorNet(nn.Module):
    def __init__(self, state_dim, hidden_dim, action_dim) -> None:
        super().__init__()
        self.fc1 = nn.Linear(state_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, action_dim)

    def forward(self, state):

        hidden_state = F.relu(self.fc1(state))
        # print(self.fc2(hidden_state))
        probs = F.softmax(self.fc2(hidden_state), dim=1)
        return probs


class A2C_TARGET:
    def __init__(self, state_dim, hidden_dim, action_dim, actor_lr, critic_lr,
                 gamma, tau, device) -> None:
        self.actor = ActorNet(state_dim, hidden_dim, action_dim).to(device)
        self.critic = CriticNet(state_dim, hidden_dim, action_dim).to(device)
        self.critic_target = CriticNet(state_dim, hidden_dim,
                                       action_dim).to(device)
        self.critic_target.load_state_dict(self.critic.state_dict())

        self.gamma = gamma
        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(),
                                                lr=actor_lr)
        self.critic_optimizer = torch.optim.Adam(self.critic.parameters(),
                                                 lr=critic_lr)
        self.device = device
        self.tau = tau

    def save_model(self, save_path='./', filename='model'):
        torch.save(self.actor.state_dict(), f"{save_path}\\{filename}.pth")

    def load_model(self, load_path):
        self.actor.load_state_dict(torch.load(load_path))

    def take_action(self, state):
        state = torch.tensor([state], dtype=torch.float).to(self.device)
        probs = self.actor(state)
        action_dist = torch.distributions.Categorical(probs)
        action = action_dist.sample()
        return action.item()

    def soft_update(self, net, target_net):
        for param_target, param in zip(target_net.parameters(),
                                       net.parameters()):
            param_target.data.copy_(param_target.data * (1 - self.tau) +
                                    param.data * self.tau)

    def update(self, transition_dict):
        rewards = torch.tensor(transition_dict['rewards'],
                               dtype=torch.float).view(-1, 1).to(self.device)
        states = torch.tensor(transition_dict['states'],
                              dtype=torch.float).to(self.device)
        actions = torch.tensor(transition_dict['actions']).view(-1, 1).to(
            self.device)
        next_states = torch.tensor(transition_dict['next_states'],
                                   dtype=torch.float).to(self.device)
        next_actions = torch.tensor(transition_dict['next_actions']).view(
            -1, 1).to(self.device)
        dones = torch.tensor(transition_dict['dones'],
                             dtype=torch.float).to(self.device).view(-1, 1)

        v_now = self.critic(states).view(-1, 1)
        v_next = self.critic_target(next_states).view(-1, 1)
        y_now = (self.gamma * v_next * (1 - dones) + rewards).view(-1, 1)
        td_delta = y_now - v_now
        log_prob = torch.log(self.actor(states).gather(1, actions))

        actor_loss = torch.mean(-log_prob * td_delta.detach())
        critic_loss = torch.mean(F.mse_loss(y_now.detach(), v_now))

        self.actor_optimizer.zero_grad()
        self.critic_optimizer.zero_grad()

        actor_loss.backward()
        critic_loss.backward()

        self.actor_optimizer.step()
        self.critic_optimizer.step()
        self.soft_update(self.critic, self.critic_target)


if __name__ == "__main__":

    env_name = 'Snake-v0'  #'CartPole-v0'

    # 注册环境
    gym.register(id='Snake-v0', entry_point='snake_env:SnakeEnv')

    env = gym.make(env_name)

    random.seed(0)
    np.random.seed(0)
    env.seed(0)
    torch.manual_seed(0)
    gamma = 0.98
    algorithm_name = "A2C_TARGET"
    num_episodes = 10000
    actor_lr = 1e-3
    critic_lr = 3e-3
    tau = 5e-3
    device = torch.device('cuda')
    state_dim = env.observation_space.shape[0]
    hidden_dim = 128
    action_dim = env.action_space.n

    agent = A2C_TARGET(state_dim, hidden_dim, action_dim, actor_lr, critic_lr,
                       gamma, tau, device)

    return_list = []
    max_reward = 0
    for i in range(10):
        with tqdm(total=int(num_episodes / 10),
                  desc='Iteration %d' % i) as pbar:
            for i_episodes in range(int(num_episodes / 10)):
                episode_return = 0
                state = env.reset()
                done = False

                transition_dict = {
                    'states': [],
                    'actions': [],
                    'next_states': [],
                    'next_actions': [],
                    'rewards': [],
                    'dones': []
                }

                while not done:
                    action = agent.take_action(state)
                    next_state, reward, done, _ = env.step(action)
                    next_action = agent.take_action(next_state)

                    transition_dict['states'].append(state)
                    transition_dict['actions'].append(action)
                    transition_dict['next_states'].append(next_state)
                    transition_dict['next_actions'].append(next_action)
                    transition_dict['rewards'].append(reward)
                    transition_dict['dones'].append(done)

                    state = next_state
                    episode_return += reward
                    if i_episodes == int(num_episodes / 10) - 1:
                        # time.sleep(0.1)
                        env.render()

                agent.update(transition_dict)

                return_list.append(episode_return)
                plot_smooth_reward(return_list, 100, env_name, algorithm_name)

                if episode_return > max_reward:
                    max_reward = episode_return
                    agent.save_model(env_name, algorithm_name)
                if (i_episodes + 1 % 10 == 0):
                    pbar.set_postfix({
                        'episode':
                        '%d' % (num_episodes / 10 * i + i_episodes + 1),
                        'return':
                        '%.3f' % np.mean(return_list[-10:])
                    })
                pbar.update(1)
