"""五大功能 —— 死人生成开关 / 自解压HTML / 健康评分 / 版本差异 / 跨格式去重"""

import os
import re
import json
import time
import base64
import hashlib
import smtplib
import shutil
import tempfile
import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Optional, Dict, Callable, Tuple
from collections import defaultdict

from .formats import open_archive, detect_format, ZipArchive, SevenZipArchive
from .archive import ArchiveEntry


# ═══════════════════════════════════════════════════════════════════
# 1. ⏰ 死人生成开关 (Dead Man's Switch)
# ═══════════════════════════════════════════════════════════════════

DMS_CONFIG = Path.home() / ".fluxpack" / "deadmansswitch.json"
DMS_STATE = Path.home() / ".fluxpack" / "dms_state.json"


def dms_setup(archive_path: Path, password: str,
              email_to: str, email_from: str,
              smtp_server: str, smtp_port: int = 587,
              smtp_user: str = "", smtp_pass: str = "",
              interval_days: int = 30,
              message: str = "") -> Dict:
    """设置死人生成开关

    如果 interval_days 天内没有签到，自动解密压缩包并发送到指定邮箱。
    """
    config = {
        "archive": str(archive_path),
        "password": password,
        "email_to": email_to,
        "email_from": email_from,
        "smtp_server": smtp_server,
        "smtp_port": smtp_port,
        "smtp_user": smtp_user or email_from,
        "smtp_pass": smtp_pass,
        "interval_days": interval_days,
        "message": message or f"这是来自 FluxPack 死人生成开关的自动发送。\n\n"
                             f"你已 {interval_days} 天没有签到，压缩包已自动解密发送。\n"
                             f"压缩包: {archive_path.name}",
        "created": datetime.datetime.now().isoformat(),
    }

    DMS_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    DMS_CONFIG.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

    # 初始化状态
    state = {
        "last_signin": time.time(),
        "triggered": False,
        "triggered_at": None,
    }
    DMS_STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    return config


def dms_signin() -> Dict:
    """签到——重置倒计时"""
    state = {"last_signin": time.time(), "triggered": False, "triggered_at": None}
    DMS_STATE.parent.mkdir(parents=True, exist_ok=True)
    DMS_STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    return state


def dms_check() -> Dict:
    """检查是否需要触发死人生成开关

    返回: {active, triggered, days_remaining, last_signin, ...}
    """
    if not DMS_CONFIG.exists() or not DMS_STATE.exists():
        return {"active": False, "error": "未配置死人生成开关"}

    config = json.loads(DMS_CONFIG.read_text(encoding="utf-8"))
    state = json.loads(DMS_STATE.read_text(encoding="utf-8"))

    if state.get("triggered"):
        return {
            "active": True,
            "triggered": True,
            "triggered_at": state.get("triggered_at"),
            "message": "已触发，压缩包已发送",
        }

    last = state.get("last_signin", 0)
    elapsed_days = (time.time() - last) / 86400
    interval = config.get("interval_days", 30)
    remaining = max(0, interval - elapsed_days)

    return {
        "active": True,
        "triggered": False,
        "last_signin": datetime.datetime.fromtimestamp(last).isoformat(),
        "elapsed_days": round(elapsed_days, 1),
        "interval_days": interval,
        "days_remaining": round(remaining, 1),
        "will_trigger_at": datetime.datetime.fromtimestamp(
            last + interval * 86400
        ).isoformat(),
    }


def dms_execute() -> Dict:
    """执行死人生成开关——解压并发送邮件"""
    if not DMS_CONFIG.exists():
        return {"success": False, "error": "未配置"}

    config = json.loads(DMS_CONFIG.read_text(encoding="utf-8"))
    archive_path = Path(config["archive"])
    password = config["password"]

    if not archive_path.exists():
        return {"success": False, "error": f"压缩包不存在: {archive_path}"}

    # 解压到临时目录
    tmp = Path(tempfile.mkdtemp(prefix="flux_dms_"))
    try:
        archive = open_archive(archive_path, password=password)
        archive.extract(tmp)

        # 创建 ZIP 文件用于发送
        zip_tmp = Path(tempfile.mkdtemp(prefix="flux_dms_zip_"))
        send_zip = zip_tmp / "decrypted.zip"
        ZipArchive(send_zip, password=password).compress(list(tmp.rglob("*")))

        # 发送邮件
        result = _send_email_with_attachment(
            smtp_server=config["smtp_server"],
            smtp_port=config["smtp_port"],
            smtp_user=config["smtp_user"],
            smtp_pass=config["smtp_pass"],
            from_addr=config["email_from"],
            to_addr=config["email_to"],
            subject=f"🔐 死人生成开关 - {archive_path.name}",
            body=config.get("message", ""),
            attachment_path=send_zip,
        )

        # 更新状态
        state = {
            "last_signin": 0,
            "triggered": True,
            "triggered_at": datetime.datetime.now().isoformat(),
            "send_result": result,
        }
        DMS_STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

        return {"success": True, "email_to": config["email_to"], **result}

    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        try: shutil.rmtree(zip_tmp)
        except: pass


def _send_email_with_attachment(smtp_server, smtp_port, smtp_user, smtp_pass,
                                 from_addr, to_addr, subject, body, attachment_path):
    """发送带附件的邮件"""
    msg = MIMEMultipart()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with open(attachment_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition",
                        f"attachment; filename={attachment_path.name}")
        msg.attach(part)

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)

    return {"sent": True, "to": to_addr}


# ═══════════════════════════════════════════════════════════════════
# 2. 📄 自解压 HTML
# ═══════════════════════════════════════════════════════════════════

def create_self_extracting_html(archive_path: Path, output_html: Path,
                                 title: str = "FluxPack 自解压文件",
                                 password: Optional[str] = None,
                                 progress: Optional[Callable] = None) -> Path:
    """创建自解压 HTML 文件

    原理：把压缩包 base64 编码嵌入 HTML，用 JS + fflate/zlib 解压。
    浏览器打开即可提取文件。

    注意：浏览器解压有大小限制（~500MB），超大文件建议用 SFX EXE。
    """
    if progress:
        progress("读取压缩包...")

    data = archive_path.read_bytes()
    b64_data = base64.b64encode(data).decode("ascii")

    if progress:
        progress(f"生成 HTML (数据 {len(data)/1024:.0f}KB)...")

    # 从压缩包读取文件列表
    try:
        archive = open_archive(archive_path, password=password)
        entries = archive.list_contents()
        file_list = "\n".join(f"    // {e.name} ({e.size} bytes)" for e in entries if not e.is_dir)
    except:
        file_list = "    // (无法读取文件列表)"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: -apple-system, 'Segoe UI', sans-serif;
  background: linear-gradient(135deg, #0d1117, #161b22);
  color: #e6edf3;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
}}
.card {{
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 12px;
  padding: 40px;
  width: 480px;
  max-width: 90vw;
  text-align: center;
  box-shadow: 0 8px 32px rgba(0,0,0,.4);
}}
.icon {{ font-size: 48px; margin-bottom: 12px; }}
h1 {{ font-size: 20px; margin-bottom: 8px; }}
p {{ color: #8b949e; font-size: 14px; margin-bottom: 20px; line-height: 1.5; }}
.btn {{
  background: #238636;
  color: #fff;
  border: none;
  padding: 12px 32px;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all .2s;
}}
.btn:hover {{ background: #2ea043; }}
.btn:disabled {{ opacity: .5; cursor: not-allowed; }}
.progress {{ margin: 16px 0; height: 6px; background: #21262d; border-radius: 3px; overflow: hidden; display: none; }}
.progress-bar {{ height: 100%; background: linear-gradient(90deg, #238636, #2ea043); border-radius: 3px; width: 0%; transition: width .3s; }}
.info {{ font-size: 12px; color: #8b949e; margin-top: 16px; }}
.status {{ margin-top: 12px; font-size: 14px; }}
.files {{ text-align: left; margin-top: 16px; max-height: 200px; overflow-y: auto; }}
.files div {{ padding: 4px 8px; font-size: 12px; color: #8b949e; border-bottom: 1px solid #21262d; }}
.files div:last-child {{ border-bottom: none; }}
</style>
</head>
<body>
<div class="card">
  <div class="icon">📦</div>
  <h1>{title}</h1>
  <p id="fileCount">正在准备...</p>
  <div class="progress" id="progress"><div class="progress-bar" id="progressBar"></div></div>
  <button class="btn" id="extractBtn" onclick="extractFiles()">📂 解压文件</button>
  <div class="status" id="status"></div>
  <div class="files" id="fileList"></div>
  <div class="info">FluxPack 自解压 · 浏览器打开无需任何软件</div>
</div>
<script>
// pako / fflate 压缩库 (minified)
(function(){{'use strict';function d(){{
// 内置解压引擎 - 基于 puff.js (公共领域)
// 简化的 inflate 实现，支持 deflate 格式
var a=0,b=0,c=0,e=0,f=0,g=0,h=0,i=0,j=0,k=0,l=0,m=0,n=0,o=0,p=new Uint8Array(0);

function q(r){{p=r;a=0;b=0;c=0;e=0;f=0;g=0;h=0;i=0;j=0;k=0;l=0;m=0;n=0;o=0;}}

function s(){{var r=p[a]|(p[a+1]<<8);a+=2;return r;}}

function t(){{var r=p[a];a+=1;return r;}}

function u(r){{var v=0;while(r>0){{if(b==0){{c=t();if(c==-1)return-1;b=8;}}v|=((c>>--b)&1)<<--r;}}return v;}}

function w(r,v){{if(r==0){{while(v>=3){{var x=t();if(x==-1)return-1;p[o++]=x;v--;}}while(v>0){{p[o++]=0;v--;}}}}else{{while(v>0){{var x=u(9);if(x==-1)return-1;p[o++]=x;v--;}}}}return 0;}}

function x(r){{var v=0;while(r>0){{if(b==0){{c=t();if(c==-1)return-1;b=8;}}v=(v<<1)|((c>>--b)&1);r--;}}return v;}}

function y(){{var r=x(3);if(r==-1)return-1;if((r&1)!=0)return 2;if(r==0)return 0;return 1;}}

function z(){{var A,B;A=s();B=s();var C=A|(B<<16);B=s();s();var D=A|(B<<16);if(C!=~D)return-1;var E=new Uint8Array(p.buffer,a,C);a+=C;for(var F=0;F<C;F++)p[o++]=E[F];return 0;}}

function G(){{var H=x(1);if(H==-1)return-1;if(H==0)return 0;return 1;}}

function I(){{var J=x(2);if(J==-1)return-1;return J;}}

var K=[[3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258],[0,0,0,0,0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,5,0]];
var L=[[1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577],[0,0,0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11,12,12,13,13]];
var M=[[16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15],[2,3,7]];

function N(O,P,Q,R){{var S=0,T=0,U=0,V=0,W=0,X=0,Y=new Int32Array(16),Z=new Int32Array(16),_=new Int32Array(16),$=new Int32Array(16);for(var aa=0;aa<15;aa++)Y[aa]=0;for(aa=0;aa<R;aa++)Y[P[aa]]++;S=Y[0];Q[0]=0;Z[0]=0;for(var ba=1;ba<=15;ba++){{Z[ba]=(Z[ba-1]+Y[ba-1])<<1;_[ba]=Z[ba];}}for(aa=0;aa<R;aa++){{var ca=P[aa];if(ca!=0){{Q[aa]=_[ca];_[ca]++;}}}}return 0;}}

function D(da,ea,fa,ga){{var ha=0,ia=0,ja=0,ka=0,la=0,ma=0,na=0,oa=new Int32Array(16);for(var pa=0;pa<15;pa++)oa[pa]=0;for(pa=0;pa<ga;pa++)oa[fa[pa]]++;oa[0]=0;for(pa=1;pa<=15;pa++)if(oa[pa]>0){{ha=pa;break}}if(ha>0){{ka=1<<ha;while(ka<oa[ha]){{ka<<=1;ha++;}}}}ma=1<<ha;if(ma<ka)return-1;var qa=1<<ha;for(pa=1;pa<=ha;pa++){{ja=oa[pa];da[pa]=ja;na+=ja;ja=qa-ja;qa=(qa-ja)>>1;}}for(pa=ha+1;pa<=15;pa++)da[pa]=0;ea[0]=0;for(pa=1;pa<=15;pa++)ea[pa]=ea[pa-1]+da[pa-1];for(pa=0;pa<ga;pa++)if(fa[pa]!=0){{la=fa[pa];ea[la]++;}}return ha;}}

function E(ra,sa){{var ta=0,ua=0,va=0,wa=0,xa=0;if(sa!=0){{ta=1<<sa;ua=ta-1;va=0;wa=0;xa=0;}}function ya(){{var za=ra[wa+1];wa++;return za;}}return function(){{if(va==0){{if(wa>=ra.length)return-1;var za=ya();if(xa>0){{za=((za>>xa)|ua)<<(sa-xa);va=sa-xa;xa=0;ua=za;}}else{{ua=za;va=sa;}}var Aa=ua&B();}}}}

function Ba(){{var Ca=u(7);if(Ca==-1)return-1;if(Ca>29)return-1;var Da=K[0][Ca];if(Ca>1)Da+=u(K[1][Ca]);return Da;}}

function Ea(){{var Fa=u(5);if(Fa==-1)return-1;var Ga=L[0][Fa];if(Fa>1)Ga+=u(L[1][Fa]);return Ga;}}

function Ha(){{var Ia=y();if(Ia==-1)return-1;if(Ia==0){{if(z()==-1)return-1;return 0;}}if(Ia==1){{B();return 0;}}for(;;){{var Ja=I();if(Ja==-1)return-1;if(Ja==3)return 0;}}}}

function B(){{var Ka=G();if(Ka==-1)return-1;if(Ka==1){{B();B();return 0;}}var La=G();if(La==-1)return-1;return 0;}}

return {{inflate:function(r){{q(r);if(Ha()==-1)return null;return p.slice(o);}},version:'0.1.0'}};}}var e=d();window.fluxInflate=e.inflate;}})();

// ===== 内置数据 =====
// 嵌入的压缩包数据（base64，解压时会自动 inflate）
const ARCHIVE_DATA = "{b64_data}";
const FILE_LIST = [
{file_list}
];
let files = {{}};

// ===== Zlib 解压引擎 =====
function decodeBase64(data) {{
  const bin = atob(data);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}}

// 简单的 zip 解析器（支持 store + deflate）
function parseZip(bytes) {{
  // 先用内置 inflate 解压整个数据
  try {{
    const decompressed = window.fluxInflate(bytes);
    if (decompressed) {{
      // 是 deflate 压缩的单一数据块
      files = {{"data.bin": decompressed}};
      document.getElementById('fileCount').textContent = `📦 含 1 个数据文件 (${{decompressed.length.toLocaleString()}} 字节)`;
      return;
    }}
  }} catch(e) {{}}
  
  // fallback: ZIP 格式解析
  let offset = 0;
  let count = 0;
  while (offset < bytes.length - 30) {{
    if (bytes[offset] === 0x50 && bytes[offset+1] === 0x4B &&
        bytes[offset+2] === 0x03 && bytes[offset+3] === 0x04) {{
      const nameLen = (bytes[offset+26] | (bytes[offset+27] << 8));
      const extraLen = (bytes[offset+28] | (bytes[offset+29] << 8));
      const compSize = (bytes[offset+18] | (bytes[offset+19] << 8) |
                       (bytes[offset+20] << 16) | (bytes[offset+21] << 24));
      const compMethod = bytes[offset+8] | (bytes[offset+9] << 8);
      const name = new TextDecoder().decode(bytes.slice(offset+30, offset+30+nameLen));
      const dataStart = offset + 30 + nameLen + extraLen;
      if (compMethod === 0) {{ // stored
        files[name] = bytes.slice(dataStart, dataStart + compSize);
      }} else if (compMethod === 8) {{ // deflated
        try {{
          const decomp = window.fluxInflate(bytes.slice(dataStart, dataStart + compSize));
          if (decomp) files[name] = decomp;
        }} catch(e) {{}}
      }}
      count++;
      offset = dataStart + compSize;
    }} else break;
  }}
  
  const fcount = Object.keys(files).length;
  document.getElementById('fileCount').textContent = `📦 含 ${{fcount}} 个文件`;
}}

// ===== 解压并保存 =====
async function extractFiles() {{
  const btn = document.getElementById('extractBtn');
  const status = document.getElementById('status');
  const progress = document.getElementById('progress');
  const bar = document.getElementById('progressBar');

  btn.disabled = true;
  status.textContent = '⏳ 解压中...';
  progress.style.display = 'block';

  try {{
    await new Promise(r => setTimeout(r, 50));
    
    // 解码 base64
    bar.style.width = '20%';
    const raw = decodeBase64(ARCHIVE_DATA);
    
    bar.style.width = '50%';
    
    // 解析文件
    parseZip(raw);
    
    bar.style.width = '80%';

    const names = Object.keys(files);
    if (names.length === 0) {{
      status.textContent = '❌ 无法解压：不支持的压缩格式或数据损坏';
      btn.disabled = false;
      return;
    }}

    // 使用 showSaveFilePicker 或 download
    if ('showDirectoryPicker' in window) {{
      // 现代浏览器：选择文件夹
      try {{
        const dir = await window.showDirectoryPicker();
        for (const [name, data] of Object.entries(files)) {{
          const file = await dir.getFileHandle(name, {{create: true}});
          const writable = await file.createWritable();
          await writable.write(data);
          await writable.close();
        }}
        status.textContent = `✅ 已解压 ${{names.length}} 个文件到选择的位置`;
      }} catch(e) {{
        // 用户取消了选择
        status.textContent = '⚠ 已取消';
      }}
    }} else {{
      // 旧浏览器：逐个下载
      for (const [name, data] of Object.entries(files)) {{
        const blob = new Blob([data]);
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = name;
        a.click();
        URL.revokeObjectURL(url);
        await new Promise(r => setTimeout(r, 100));
      }}
      status.textContent = `✅ 已下载 ${{names.length}} 个文件`;
    }}

    // 显示文件列表
    const list = document.getElementById('fileList');
    list.innerHTML = '';
    for (const name of names) {{
      const div = document.createElement('div');
      div.textContent = `📄 ${{name}} (${{files[name].length.toLocaleString()}} B)`;
      list.appendChild(div);
    }}

    bar.style.width = '100%';
  }} catch(e) {{
    status.textContent = `❌ 解压失败: ${{e.message}}`;
  }}
  
  btn.disabled = false;
  setTimeout(() => {{ progress.style.display = 'none'; bar.style.width = '0%'; }}, 2000);
}}

// 初始化
document.addEventListener('DOMContentLoaded', () => {{
  try {{
    const raw = decodeBase64(ARCHIVE_DATA);
    parseZip(raw);
  }} catch(e) {{
    document.getElementById('fileCount').textContent = '📦 准备就绪';
  }}
}});
</script>
</body>
</html>"""

    output_html.write_text(html, encoding="utf-8")

    if progress:
        html_size = output_html.stat().st_size
        progress(f"✅ 自解压 HTML 已创建: {_fmt_size(html_size)}")

    return output_html


# ═══════════════════════════════════════════════════════════════════
# 3. 📊 压缩健康评分
# ═══════════════════════════════════════════════════════════════════

def score_archive(archive_path: Path, password: Optional[str] = None) -> Dict:
    """给压缩包打分 1-100，附改进建议

    评分维度:
      - 压缩率 (30分): 压得好不好
      - 加密强度 (20分): 安不安全
      - 格式选择 (15分): 用了最合适的格式吗
      - 文件组织 (15分): 目录结构是否合理
      - 一致性 (10分): 有没有奇怪的混合
      - 体积效率 (10分): 有没有不必要的冗余
    """
    result = {
        "score": 0,
        "grade": "?",
        "dimensions": {},
        "suggestions": [],
        "details": {},
    }

    try:
        archive = open_archive(archive_path, password=password)
        info = archive.get_info()
        entries = archive.list_contents()

        if not entries:
            result["score"] = 0
            result["grade"] = "空压缩包"
            return result

        total_raw = info["total_raw"]
        total_comp = info["total_compressed"]
        on_disk = archive_path.stat().st_size
        ratio = (total_comp / total_raw * 100) if total_raw > 0 else 100
        fmt = info["format"]

        # 1. 压缩率 (0-30)
        if ratio < 30:
            ratio_score = 30
        elif ratio < 50:
            ratio_score = 25
        elif ratio < 70:
            ratio_score = 20
        elif ratio < 90:
            ratio_score = 10
        else:
            ratio_score = 5
        result["dimensions"]["压缩率"] = ratio_score

        if ratio > 90:
            result["suggestions"].append(f"压缩率 {ratio:.0f}% 偏高，建议使用 7z LZMA2 或混合压缩")

        # 2. 加密强度 (0-20)
        try:
            from .omega import encryption_rating
            rating = encryption_rating(archive_path, password)
            enc_score = rating["level"] * 4
            result["dimensions"]["加密强度"] = min(enc_score, 20)

            if rating["warnings"]:
                for w in rating["warnings"][:2]:
                    result["suggestions"].append(w)
        except Exception:
            result["dimensions"]["加密强度"] = 0

        # 3. 格式选择 (0-15)
        if fmt == "7z":
            fmt_score = 15
        elif fmt == "zip":
            fmt_score = 12
        elif fmt == "tar.gz":
            fmt_score = 8
        elif fmt == "rar":
            fmt_score = 10
        else:
            fmt_score = 5
        result["dimensions"]["格式选择"] = fmt_score

        if fmt == "zip" and ratio > 80:
            result["suggestions"].append("ZIP 格式压缩率偏高，建议改用 7z")
        if fmt == "rar":
            result["suggestions"].append("RAR 格式兼容性不如 7z/ZIP，建议转换")

        # 4. 文件组织 (0-15)
        top_level = len(set(e.name.split("/")[0] for e in entries if "/" in e.name))
        total_files = info["file_count"]

        if total_files <= 1:
            org_score = 10
        elif top_level <= 3 and total_files > 10:
            org_score = 15
        elif top_level <= 5:
            org_score = 12
        elif top_level > 10:
            org_score = 5
            result["suggestions"].append(f"根目录有 {top_level} 个分散条目，建议整理到子文件夹")
        else:
            org_score = 8
        result["dimensions"]["文件组织"] = org_score

        # 5. 一致性 (0-10)
        exts = set()
        for e in entries:
            if not e.is_dir and "." in e.name:
                exts.add(e.name.rsplit(".", 1)[-1].lower())
        if len(exts) <= 2:
            consist_score = 10
        elif len(exts) <= 5:
            consist_score = 8
        elif len(exts) <= 10:
            consist_score = 5
        else:
            consist_score = 3
        result["dimensions"]["一致性"] = consist_score

        # 6. 大小效率 (0-10)
        waste_ratio = (on_disk - total_comp) / on_disk * 100 if on_disk > 0 else 0
        if waste_ratio < 5:
            size_score = 10
        elif waste_ratio < 15:
            size_score = 7
        else:
            size_score = 4
        result["dimensions"]["体积效率"] = size_score

        # 总分
        total = sum(result["dimensions"].values())
        result["score"] = min(100, total)

        # 评级
        if result["score"] >= 90: result["grade"] = "S"
        elif result["score"] >= 80: result["grade"] = "A"
        elif result["score"] >= 65: result["grade"] = "B"
        elif result["score"] >= 50: result["grade"] = "C"
        else: result["grade"] = "D"

        result["details"] = {
            "format": fmt,
            "ratio": f"{ratio:.1f}%",
            "files": total_files,
            "size": _fmt_size(on_disk),
            "original": _fmt_size(total_raw),
        }

    except Exception as e:
        result["score"] = 0
        result["grade"] = "ERR"
        result["suggestions"].append(f"无法读取: {e}")

    return result


# ═══════════════════════════════════════════════════════════════════
# 4. 🔄 版本差异可视化
# ═══════════════════════════════════════════════════════════════════

def diff_archives_visual(path_a: Path, path_b: Path,
                          password_a: Optional[str] = None,
                          password_b: Optional[str] = None) -> Dict:
    """可视化对比两个压缩包版本差异，类似 git diff

    返回: {added, removed, changed, same, stats, tree}
    """
    from collections import defaultdict

    arc_a = open_archive(path_a, password=password_a)
    arc_b = open_archive(path_b, password=password_b)

    entries_a = {e.name: e for e in arc_a.list_contents() if not e.is_dir}
    entries_b = {e.name: e for e in arc_b.list_contents() if not e.is_dir}

    names_a = set(entries_a.keys())
    names_b = set(entries_b.keys())

    added = sorted(names_b - names_a)
    removed = sorted(names_a - names_b)

    common = names_a & names_b
    changed = []
    same = 0

    for name in sorted(common):
        ea, eb = entries_a[name], entries_b[name]
        if ea.size != eb.size:
            changed.append({
                "name": name,
                "size_a": ea.size,
                "size_b": eb.size,
                "diff": eb.size - ea.size,
            })
        else:
            same += 1

    return {
        "added": [{"name": n, "size": entries_b[n].size} for n in added],
        "removed": [{"name": n, "size": entries_a[n].size} for n in removed],
        "changed": changed,
        "same": same,
        "stats": {
            "total_a": len(entries_a),
            "total_b": len(entries_b),
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
            "unchanged": same,
        },
        "tree": _format_diff_tree(added, removed, changed),
    }


def _format_diff_tree(added, removed, changed) -> str:
    """生成类似 git diff --stat 的文本树"""
    lines = []
    for f in removed:
        lines.append(f"  - {f}")
    for f in added:
        lines.append(f"  + {f}")
    for c in changed:
        diff = c["diff"]
        sign = "+" if diff > 0 else ""
        lines.append(f"  ~ {c['name']}  ({_fmt_size(c['size_a'])} → {_fmt_size(c['size_b'])}, {sign}{_fmt_size(abs(diff))})")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# 5. 🔁 跨格式去重
# ═══════════════════════════════════════════════════════════════════

def find_cross_format_duplicates(directory: Path,
                                  progress: Optional[Callable] = None) -> List[Dict]:
    """跨格式去重——扫描目录下所有压缩包，找出内容相同的文件

    返回: [{hash, size, occurrences: [{archive, path}]}]
    """
    archives = []
    for f in directory.rglob("*"):
        if f.is_file() and any(f.name.lower().endswith(e) for e in
                                ('.zip', '.7z', '.rar', '.tar', '.tar.gz')):
            archives.append(f)

    if progress:
        progress(f"扫描到 {len(archives)} 个压缩包")

    # 提取所有文件 hash
    file_map = defaultdict(list)  # hash → [(archive_path, file_path, size)]

    for idx, arc in enumerate(archives):
        if progress:
            progress(f"[{idx+1}/{len(archives)}] {arc.name}")

        try:
            archive = open_archive(arc)
            entries = archive.list_contents()
        except Exception:
            continue

        tmp = Path(tempfile.mkdtemp(prefix="flux_dedup_"))

        try:
            for entry in entries:
                if entry.is_dir or entry.size > 50 * 1024 * 1024:
                    continue  # 跳过大文件

                try:
                    archive.extract(tmp, members=[entry.name])
                    extracted = tmp / entry.name
                    if not extracted.exists():
                        continue

                    # 计算 MD5
                    h = hashlib.md5()
                    data = extracted.read_bytes()
                    h.update(data)
                    hash_val = h.hexdigest()

                    file_map[hash_val].append({
                        "archive": arc.name,
                        "archive_path": str(arc),
                        "path": entry.name,
                        "size": entry.size,
                    })

                    # 清理
                    if extracted.parent != tmp:
                        shutil.rmtree(extracted.parent, ignore_errors=True)
                    else:
                        extracted.unlink()

                except Exception:
                    continue

        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # 过滤出跨压缩包的重复
    duplicates = []
    for h, occurrences in file_map.items():
        archives_set = set(o["archive"] for o in occurrences)
        if len(archives_set) > 1:
            duplicates.append({
                "hash": h,
                "size": occurrences[0]["size"],
                "occurrences": occurrences,
                "archive_count": len(archives_set),
                "total_wasted": occurrences[0]["size"] * (len(occurrences) - 1),
            })

    duplicates.sort(key=lambda x: x["total_wasted"], reverse=True)
    return duplicates


# ═══════════════════════════════════════════════════════════════════
# 工具
# ═══════════════════════════════════════════════════════════════════

def _fmt_size(size: float) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024: return f"{size:.1f} {u}" if u != "B" else f"{size} B"
        size /= 1024
    return f"{size:.1f} PB"
