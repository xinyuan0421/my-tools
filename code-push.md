每次更新代码的标准流程：
# 1. 进入仓库目录
cd /home/tsdl/HDD/Tool/my-tools

# 2. 查看改动了哪些文件（可选）
git status

# 3. 将改动加入暂存区
git add .                        # 添加所有改动
# 或指定文件：git add 文件名

# 4. 提交并写说明
git commit -m "描述这次改了什么"

# 5. 推送到 GitHub
git push

拉取最新代码的流程：
# 1. 进入仓库目录
cd /home/tsdl/HDD/Tool/my-tools

# 2. 拉取并合并远程最新代码
git pull

如果本地有未提交的改动，建议先处理：
# 方式一：先提交本地改动，再拉取
git add .
git commit -m "本地改动说明"
git pull

# 方式二：暂存本地改动，拉取后再恢复
git stash        # 暂存
git pull         # 拉取
git stash pop    # 恢复

#新建文件夹clone代码的命令
git clone git@github.com:xinyuan0421/my-tools.git


#注意：新机器首次使用需先配置 SSH 密钥，否则改用 HTTPS 方式：
git clone https://github.com/xinyuan0421/my-tools.git

