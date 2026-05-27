# 在腾讯云网页终端用 root 执行（整段复制粘贴）

mkdir -p /home/ai-service/.ssh
echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDo6pWX3QFs74ui5x6bnWFdJ5RuMLSRmmuUKOOO+jmdl administrator@PC-202011172203" >> /home/ai-service/.ssh/authorized_keys
chmod 700 /home/ai-service/.ssh
chmod 600 /home/ai-service/.ssh/authorized_keys
chown -R ai-service:ai-service /home/ai-service/.ssh
