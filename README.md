<div align="center">

# ⚡ FluxPack

**轻量压缩包管理器 — 压/解/破/搜/管，一体搞定**

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-brightgreen)](https://github.com)
[![Tests](https://img.shields.io/badge/Tests-73%20passed-brightgreen)](tests/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

</div>

---

## 📸 截图

```
⚡ FluxPack                                          [☀ 亮色]  就绪
┌─────────────────────────────────────────────────────────────────┐
│ 📦 压缩  📂 解压  📋 浏览  🔓 破解  🔄 转换  ✅ 校验          │
│ 🆚 对比  🔧 修复  🧹 清理  📊 分析  🔮 智能                   │
│ 🔍 扫描  ✏️ 编辑  🧬 混合  🔧 管道  🖱 集成                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## ✨ 功能概览

### 核心操作
| 功能 | 说明 | CLI |
|------|------|-----|
| 压缩 | ZIP/7Z/TAR.GZ/RAR，密码加密，分卷 | `flux compress` |
| 解压 | 所有格式，密码解压，选择性解压 | `flux extract` |
| 浏览 | 文件列表，CRC，压缩比 | `flux list` |
| 信息 | 格式/大小/文件数/加密详情 | `flux info` |
| 校验 | 完整性检测 | `flux test` |

### 🔓 密码破解
| 方法 | 说明 | 速度 |
|------|------|------|
| 字典攻击 | 内置 200+ 常用密码 + 自定义字典 | ~13 pwd/s |
| 暴力破解 | 穷举所有组合（多线程） | ~13 pwd/s x 线程 |
| 智能模式 | 字典→年份→数字，自动推进 | 自动 |
| 掩码攻击 | 类似 hashcat 的 `?l?l?d?d` 模式 | 可配 |
| hashcat GPU | 调用外部 hashcat，100M+ pwd/s | ⚡极限 |
| 批量解锁 | 一个密码列表试多个包 | 自动 |

### 🧬 高级压缩
- **多算法混合**：文本→PPMd，EXE→LZMA2极限，图片→Store，同一包内各取最优
- **图片优化打包**：JPEG重压缩 + PNG优化 + EXIF剥离 → 7Z打包，省 30-50%
- **压缩竞赛**：同时用 ZIP/7Z/TAR/TAR.GZ 压一遍，数据对比推荐
- **压缩模拟**：采样 5% 文件测试，不真压也能知道结果
- **压缩预设**：保存常用参数为命名模板，一键复用

### 🔧 管道引擎
链式操作：`下载 → 解压 → 清理 → 去重 → 优化图片 → 压缩 → 分卷 → 校验`

```
download url=https://example.com/photos.zip
extract
clean
optimize_images jpeg_quality=80
dedup
compress output=final.7z hybrid=true
split volume=10M
checksum
```

### 🔎 搜索与分析
- **全盘压缩包搜索**：建立文件名索引，秒搜包内文件（类似 Everything）
- **跨包全文搜索**：在多个压缩包中搜索文件内容
- **健康报告**：全盘压缩包体检（损坏/加密/格式分布）
- **空间浪费分析**：找压缩率最差的包，算可节省空间
- **版本差异**：像 git diff 一样对比两个压缩包

### 🛡️ 安全
- **ZIP 炸弹检测**：解压前分析压缩比，50x 警告 / 200x 阻止
- **密码强度评估**：实时计算 + hashcat 破解时间估算
- **隐写检测**：检查 ZIP 注释/尾部多余数据
- **加密强度评级**：ZIP2.0 / AES128/256 / RAR5 分级
- **蜜罐压缩包**：创建假加密包，记录谁尝试打开

### 🤖 自动化
- **文件夹监控**：新文件自动压缩归档（`flux watch`）
- **死人生成开关**：30 天不签到自动解密发邮件
- **增量备份**：只打包变化文件
- **时光机**：操作前自动备份，可撤销

### 📦 分发
- **自解压 EXE**：生成 `.exe`，对方双击即解压
- **自解压 HTML**：生成 `.html`，浏览器打开即可解压
- **格式转换**：ZIP ↔ 7Z ↔ TAR.GZ 互转

### 🖱 系统集成
- **右键菜单**：文件上右键→压缩/解压/竞赛
- **文件关联**：双击 .7z/.zip/.rar 自动用 FluxPack 打开
- **拖拽压缩**：文件拖到 EXE 上自动填入 GUI

---

## 🚀 快速开始

### Windows

```bash
# 下载最新版
https://github.com/Patrick130306/fluxpack/releases

# 或从源码运行
git clone https://github.com/Patrick130306/fluxpack.git
cd fluxpack
pip install -r requirements.txt
python run_launcher.py gui

# 安装右键菜单（管理员）
FluxPack.exe shell-install

# 安装文件关联（管理员）
FluxPack.exe ext-register
```

### Linux / macOS

```bash
git clone https://github.com/Patrick130306/fluxpack.git
cd fluxpack
pip install -r requirements.txt

# 安装
bash install.sh

# 运行
fluxpack gui          # 桌面 GUI
fluxpack --help       # CLI 帮助
```

---

## 📖 CLI 参考

### 核心命令
| 命令 | 说明 | 示例 |
|------|------|------|
| `compress` | 压缩 | `flux compress -p secret -v 10M out.7z file.txt` |
| `extract` | 解压 | `flux extract -p secret archive.7z ./out` |
| `list` | 列出内容 | `flux list archive.7z` |
| `info` | 详细信息 | `flux info archive.7z` |
| `test` | 完整性校验 | `flux test archive.7z` |

### 破解
| 命令 | 说明 | 示例 |
|------|------|------|
| `crack` | 密码破解 | `flux crack -m smart secret.7z` |
| `hashcat` | GPU 加速 | `flux hashcat secret.7z -w rockyou.txt` |
| `pwdstrength` | 密码强度 | `flux pwdstrength "MyP@ss!"` |

### 压缩
| 命令 | 说明 | 示例 |
|------|------|------|
| `simulate` | 模拟压缩 | `flux simulate bigfile.bin` |
| `battle` | 压缩竞赛 | `flux battle doc.pdf` |
| `profile` | 预设管理 | `flux profile list` |
| `htmlsfx` | 自解压 HTML | `flux htmlsfx archive.7z out.html` |
| `sfx` | 自解压 EXE | `flux sfx archive.7z out.exe` |

### 安全
| 命令 | 说明 | 示例 |
|------|------|------|
| `bombcheck` | ZIP 炸弹检测 | `flux bombcheck suspicious.7z` |
| `honeypot` | 蜜罐管理 | `flux honeypot create decoy.7z` |

### 自动化和工具
| 命令 | 说明 | 示例 |
|------|------|------|
| `watch` | 文件夹监控 | `flux watch ./inbox --format 7z` |
| `dms` | 死人生成开关 | `flux dms setup ...` |
| `index` | 压缩包搜索 | `flux index build . && flux index search 合同` |
| `savings` | 节省统计 | `flux savings` |
| `organize` | 文件组织 | `flux organize ./乱文件夹` |
| `xdedup` | 跨格式去重 | `flux xdedup ./archives` |
| `diff-visual` | 版本差异 | `flux diff-visual v1.7z v2.7z` |
| `archive-score` | 健康评分 | `flux archive-score my.7z` |

### 系统集成
| 命令 | 说明 | 示例 |
|------|------|------|
| `shell-install` | 装右键菜单 | `flux shell-install` |
| `shell-uninstall` | 卸右键菜单 | `flux shell-uninstall` |
| `ext-register` | 文件关联 | `flux ext-register` |
| `gui` | 启动桌面 GUI | `flux gui` |

---

## 📁 项目结构

```
fluxpack/
├── run_launcher.py    # 入口（双击→GUI，有参数→CLI）
├── run_gui.py         # GUI 快捷入口
├── install.sh         # Linux 安装脚本
├── fluxpack.spec      # PyInstaller 打包配置
├── requirements.txt   # 依赖
├── README.md
├── src/
│   ├── main.py        # 模块入口
│   ├── core/
│   │   ├── archive.py     # 压缩包抽象基类
│   │   ├── formats.py     # ZIP/7Z/RAR/TAR 适配器
│   │   ├── cracker.py     # 密码破解引擎
│   │   ├── advanced.py    # diff/修复/去重/校验/预览/清理 (15+功能)
│   │   ├── hybrid.py      # 多算法混合压缩 + 图片优化
│   │   ├── operations.py  # 格式转换/批量操作
│   │   ├── power.py       # 右键菜单/竞赛/批量解锁
│   │   ├── finale.py      # 文件关联/预设/模拟器
│   │   ├── nuclear.py     # hashcat加速/文件夹监控/自解压EXE
│   │   ├── omega.py       # 炸弹检测/密码强度/索引/节省/蜜罐
│   │   └── phi.py         # 死人生成/自解压HTML/评分/差异/去重
│   └── ui/
│       ├── cli.py         # CLI 接口（50+ 命令）
│       ├── desktop.py     # 桌面 GUI（CustomTkinter，科技感主题）
│       └── templates/     # 前端模板
├── tests/
│   ├── test_archive.py    # 基础格式测试 (20)
│   ├── test_advanced.py   # 高级功能测试 (23)
│   ├── test_features.py   # 特色功能测试 (16)
│   └── test_security.py   # 安全功能测试 (22)
└── dist/
    └── FluxPack.exe       # 打包后的单文件 EXE (~30MB)
```

---

## 🔧 自行打包

```bash
# 安装 PyInstaller
pip install pyinstaller

# 打包
pyinstaller fluxpack.spec --noconfirm

# 输出: dist/FluxPack.exe (~30MB)
```

---

## 🧪 测试

```bash
# 运行全部测试
python -m pytest tests/ -v

# 运行特定测试
python -m pytest tests/test_archive.py -v

# 73 个测试，全通过
```

---

## 📦 技术栈

- **GUI**: [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter)
- **CLI**: [Click](https://click.palletsprojects.com/) + [Rich](https://rich.readthedocs.io/)
- **压缩**: `py7zr`, `pyzipper`, `rarfile`, `zipfile`, `tarfile`
- **图片**: `Pillow`, `piexif`
- **打包**: PyInstaller
- **监控**: `watchdog`
- **测试**: pytest

---

## 📄 License

MIT License

---

<div align="center">
Made with ⚡ by 章振威
</div>
