# 依赖管理

## 环境

- Python：3.11.9
- 虚拟环境：`D:\C题文件代码DEEPSEEK专用\Q2=Q3\.venv`
- 锁定文件：`requirements-lock.txt`

## 安装

```powershell
& '.\.venv\Scripts\python.exe' -m pip install -r requirements-lock.txt
```

## 检查

```powershell
& '.\.venv\Scripts\python.exe' -m pip check
& '.\.venv\Scripts\python.exe' -m pytest -q
```

依赖只安装在本工作区虚拟环境中，不修改系统 Python。

