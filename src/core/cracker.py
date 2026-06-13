"""密码恢复工具 —— 字典攻击 + 暴力破解 + 掩码攻击"""

import itertools
import string
import time
import tempfile
import shutil
from pathlib import Path
from typing import Callable, Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from .formats import open_archive


BUILTIN_DICT = [
    "123456","password","12345678","qwerty","123456789","12345","1234",
    "111111","1234567","sunshine","qwerty123","iloveyou","princess",
    "admin","welcome","666666","abc123","football","123123","monkey",
    "654321","charlie","aa123456","donald","password1","qwerty12345",
    "1234567890","letmein","passw0rd","trustno1","dragon","master",
    "hunter","ranger","abcdef","asdfgh","pass@123","P@ssw0rd","pass123",
    "test123","test1234","admin123","administrator","root","toor",
    "zaq1xsw2","qwertyuiop","asdfghjkl","zxcvbnm","1q2w3e4r","1qaz2wsx",
    "qwerty123456","flower","lovely","beautiful","sunny","password123",
    "Password123","Password@123","qwerty2024","secret","changeme",
    "default","guest","temp123","123qwe","qwe123","1q2w3e","123qweasd",
    "pass123456","hello123","helloworld","world123","welcome123",
    "iloveyou123","love123","angel","butterfly","freedom","nothing",
    "whatever","forever","shadow","shadows","superman","batman",
    "ironman","spiderman","pokemon","naruto","goku","vegeta","sasuke",
    "kakashi","starwars","thomas","george","william","james","robert",
    "michael","david","richard","joseph","charles","jennifer","michelle",
    "summer","winter","spring","autumn","october","november","december",
    "monkey123","dragon123","master123","hunter123","abc123456","xyz123",
    "987654","987654321","000000","112233","121212","131313","232323",
    "010101","passwd","pass1234","pass@1234","pass!123","Admin123",
    "Root123","Test123","User123","demo123","company123","office123",
    "school123","college123","china123","beijing123","shanghai",
    "zhang123","wang123","li123","chen123","yang123",
    "abcd1234","a123456","a1234567","a12345678","qwerty1","qwerty12",
    "123456a","123456ab","123456abc","123qwe!@#","1qaz@WSX",
    "pass12345678","password1234","password12345","admin2024","pass2024",
    "test2024","hello2024","Welcome1","Welcome123","Changeme1",
    "test@123","admin@123","root@123","demo@123",
    "woaini","woai","5201314","1314520","aini","520","1314",
    "qq123456","taobao","wechat","weixin",
    "wang1234","zhang1234","li1234","chen1234",
]


def _try_one_password(args) -> Optional[str]:
    """测试单个密码（独立函数，可被多线程调用）"""
    archive_path, password = args
    try:
        archive = open_archive(Path(archive_path), password=password)
        entries = archive.list_contents()
        if not entries:
            return None
        # 必须实际提取一个文件来验证密码
        text_files = [e for e in entries if not e.is_dir and e.size < 1024 * 1024]
        if not text_files:
            text_files = [e for e in entries if not e.is_dir]
        if text_files:
            tmp = Path(tempfile.mkdtemp(prefix="fcv_"))
            try:
                archive.extract(tmp, members=[text_files[0].name])
                extracted = tmp / text_files[0].name
                if extracted.exists() and extracted.stat().st_size > 0:
                    return password
                for f in tmp.rglob("*"):
                    if f.is_file() and f.stat().st_size > 0:
                        return password
                return None
            except Exception:
                return None
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        return None
    except Exception:
        return None


class CrackResult:
    def __init__(self):
        self.found: bool = False
        self.password: Optional[str] = None
        self.attempts: int = 0
        self.elapsed: float = 0.0
        self.speed: float = 0.0
        self.method: str = ""

    @property
    def summary(self) -> str:
        if self.found:
            return (f"✅ 破解成功！密码: [bold green]{self.password}[/]\n"
                    f"   方法: {self.method} | 尝试: {self.attempts:,} 次 | "
                    f"用时: {self.elapsed:.1f}s | 速度: {self.speed:.0f} pwd/s")
        return (f"❌ 未找到密码\n   尝试: {self.attempts:,} 次 | "
                f"用时: {self.elapsed:.1f}s | 速度: {self.speed:.0f} pwd/s")


class PasswordCracker:
    def __init__(self, archive_path: Path, callback: Optional[Callable] = None):
        self.archive_path = archive_path
        self.callback = callback
        self._winner = None  # 多线程共享的找到标志

    def _cancel_remaining(self, executor):
        """取消线程池中未开始的任务"""
        try:
            for f in list(executor._threads.keys() if hasattr(executor, '_threads') else []):
                pass
        except:
            pass

    # ── 核心：遍历密码列表，找到为止 ──────────────────

    def _try_list(self, passwords: List[str], num_workers: int,
                  result: CrackResult, start: float) -> bool:
        """遍历密码列表，找到返回 True。支持多线程。"""
        total = len(passwords)

        if num_workers <= 1:
            # 单线程：直接顺序试
            for idx, pwd in enumerate(passwords):
                result.attempts = idx + 1
                if _try_one_password((str(self.archive_path), pwd)):
                    result.found = True; result.password = pwd
                    result.elapsed = time.time() - start
                    result.speed = result.attempts / result.elapsed if result.elapsed > 0 else 0
                    return True
                if self.callback and idx % 10 == 0:
                    e = time.time() - start; s = result.attempts / e if e > 0 else 0
                    self.callback(result.attempts, total, pwd, s)
            return False

        # 多线程：先把所有任务提交，轮询检查完成情况
        # 一旦发现密码，立即返回，不等待其他线程
        executor = ThreadPoolExecutor(max_workers=num_workers)
        try:
            submitted = {executor.submit(_try_one_password, (str(self.archive_path), p)): p
                         for p in passwords}
            done_count = 0
            for future in as_completed(submitted):
                done_count += 1
                result.attempts = done_count
                pwd = future.result()
                if pwd:
                    result.found = True; result.password = pwd
                    result.elapsed = time.time() - start
                    result.speed = result.attempts / result.elapsed if result.elapsed > 0 else 0
                    return True
                if self.callback and done_count % 10 == 0:
                    e = time.time() - start; s = result.attempts / e if e > 0 else 0
                    self.callback(result.attempts, total, submitted[future], s)
            return False
        finally:
            executor.shutdown(wait=False)  # 不等待，立即返回

    # ── 字典攻击 ─────────────────────────────────────

    def dict_attack(self, wordlist: Optional[List[str]] = None,
                    num_workers: int = 4) -> CrackResult:
        result = CrackResult()
        result.method = "字典攻击"
        start = time.time()
        words = wordlist or BUILTIN_DICT
        self._try_list(words, num_workers, result, start)
        result.elapsed = time.time() - start
        result.speed = result.attempts / result.elapsed if result.elapsed > 0 else 0
        return result

    def dict_attack_from_file(self, wordlist_path: Path,
                              num_workers: int = 4) -> CrackResult:
        result = CrackResult()
        result.method = f"字典攻击 ({wordlist_path.name})"
        start = time.time()
        try:
            words = wordlist_path.read_text("utf-8", errors="ignore").splitlines()
            words = [w.strip() for w in words if w.strip()]
        except Exception:
            result.elapsed = time.time() - start
            return result
        self._try_list(words, num_workers, result, start)
        result.elapsed = time.time() - start
        result.speed = result.attempts / result.elapsed if result.elapsed > 0 else 0
        return result

    # ── 暴力破解 ────────────────────────────────────

    def brute_force(self, charset: str = string.digits,
                    min_len: int = 1, max_len: int = 6,
                    num_workers: int = 4) -> CrackResult:
        result = CrackResult()
        cs_desc = charset[:15] + "…" if len(charset) > 15 else charset
        result.method = f"暴力破解 ({cs_desc}, {min_len}-{max_len}位)"
        start = time.time()
        total = sum(len(charset)**n for n in range(min_len, max_len + 1))

        for length in range(min_len, max_len + 1):
            combos = [''.join(c) for c in itertools.product(charset, repeat=length)]
            if self._try_list(combos, num_workers, result, start):
                result.elapsed = time.time() - start
                result.speed = result.attempts / result.elapsed if result.elapsed > 0 else 0
                return result

        result.elapsed = time.time() - start
        result.speed = result.attempts / result.elapsed if result.elapsed > 0 else 0
        return result

    # ── 智能模式 ────────────────────────────────────

    def smart_attack(self, num_workers: int = 4) -> CrackResult:
        strategies = [
            ("内置字典", self._try_list, [BUILTIN_DICT, num_workers]),
        ]
        result = CrackResult()
        start = time.time()

        # 1. 字典
        result.method = "内置字典"
        self._try_list(BUILTIN_DICT, num_workers, result, start)
        if result.found:
            result.method = f"智能破解 → 内置字典"
            result.elapsed = time.time() - start
            result.speed = result.attempts / result.elapsed if result.elapsed > 0 else 0
            return result

        # 2. 4-8位纯数字
        result.method = f"智能破解 → 年份组合"
        for length in range(4, 9):
            combos = [''.join(c) for c in itertools.product("0123456789", repeat=length)]
            if self._try_list(combos, num_workers, result, start):
                result.elapsed = time.time() - start; return result

        # 3. 1-6位纯数字
        result.method = f"智能破解 → 纯数字"
        for length in range(1, 7):
            combos = [''.join(c) for c in itertools.product("0123456789", repeat=length)]
            if self._try_list(combos, num_workers, result, start):
                result.elapsed = time.time() - start; return result

        result.elapsed = time.time() - start
        return result

    # ── 掩码攻击 ────────────────────────────────────

    def mask_attack(self, masks: List[str],
                    charset_map: Optional[dict] = None,
                    num_workers: int = 4) -> CrackResult:
        if charset_map is None:
            charset_map = {
                "?l": string.ascii_lowercase, "?u": string.ascii_uppercase,
                "?d": string.digits, "?s": "!@#$%^&*()-_=+[]{}|;:',.<>?/`~",
                "?a": string.ascii_letters + string.digits + "!@#$%^&*()",
            }
        result = CrackResult()
        result.method = f"掩码攻击 ({', '.join(masks)})"
        start = time.time()

        for mask in masks:
            charsets = []
            i = 0
            while i < len(mask):
                if mask[i] == "?" and i + 1 < len(mask):
                    t = mask[i:i+2]
                    charsets.append(charset_map.get(t, t)); i += 2
                else:
                    charsets.append(mask[i]); i += 1
            if not charsets:
                continue
            combos = [''.join(c) for c in itertools.product(*charsets)]
            if self._try_list(combos, num_workers, result, start):
                result.elapsed = time.time() - start
                result.speed = result.attempts / result.elapsed if result.elapsed > 0 else 0
                return result

        result.elapsed = time.time() - start
        result.speed = result.attempts / result.elapsed if result.elapsed > 0 else 0
        return result
