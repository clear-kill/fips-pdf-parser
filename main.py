"""Download and extract public PDF documents from fips.ru pages."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import re
import os
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from tkinter import END, BOTH, LEFT, RIGHT, TOP, X, Y, Button, Entry, Frame, Label, Listbox, StringVar, Tk, filedialog, messagebox
from tkinter import ttk
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://new.fips.ru"
REGISTER_URL = f"{BASE_URL}/registers-web/"
SEARCH_URL = f"{BASE_URL}/registers-doc-view/fips_servlet"
USER_AGENT = "fips-patent-parser/1.0"

REGISTRIES = {
	"Изобретения": "RUPAT",
	"Полезные модели": "RUPM",
	"Промышленные образцы": "RUDE",
}


@dataclass
class PatentRecord:
	number: str
	registry: str
	title: str
	text: str
	html: str
	source_url: str = SEARCH_URL


class FipsError(RuntimeError):
	"""A user-facing error returned by the FIPS service."""


class FipsClient:
	def __init__(self) -> None:
		self.session = requests.Session()
		self.session.headers.update({"User-Agent": USER_AGENT})

	def get_record(self, number: str, registry_name: str) -> PatentRecord:
		registry_code = REGISTRIES[registry_name]
		self.session.get(REGISTER_URL, timeout=30).raise_for_status()
		response = self.session.post(
			SEARCH_URL,
			data={
				"DB": registry_code,
				"DocNumber": number,
				"TypeFile": "html",
				"searchPar": "par_5",
				"searchParValue": number,
			},
			timeout=30,
		)
		response.raise_for_status()
		response.encoding = "windows-1251"
		soup = BeautifulSoup(response.text, "html.parser")
		text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
		title = soup.title.get_text(" ", strip=True) if soup.title else f"Документ № {number}"
		if not text or self._is_not_found(text):
			raise FipsError(f"Документ № {number} не найден в реестре «{registry_name}».")
		html = inline_images(response.text, response.url, self.session)
		return PatentRecord(number, registry_name, title, text, html)

	@staticmethod
	def _is_not_found(text: str) -> bool:
		lowered = text.lower()
		return "документ не найден" in lowered or "не найдено" in lowered or "ошибка поиска" in lowered


def safe_filename(value: str) -> str:
	return re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("._") or "document"


def inline_images(html: str, page_url: str, session: requests.Session) -> str:
	soup = BeautifulSoup(html, "html.parser")
	for image in soup.find_all("img", src=True):
		source = image.get("src", "")
		if source.startswith("data:"):
			continue
		try:
			response = session.get(urljoin(page_url, source), timeout=30)
			response.raise_for_status()
			mime_type = response.headers.get("content-type") or mimetypes.guess_type(source)[0] or "image/jpeg"
			encoded = base64.b64encode(response.content).decode("ascii")
			image["src"] = f"data:{mime_type};base64,{encoded}"
		except requests.RequestException:
			continue
	return str(soup)


def save_record_as_pdf(record: PatentRecord, output_dir: Path) -> Path:
	output_dir.mkdir(parents=True, exist_ok=True)
	path = output_dir / f"{safe_filename(record.registry)}_{safe_filename(record.number)}.pdf"
	browser = find_browser()
	with tempfile.TemporaryDirectory(prefix="fips-print-") as temporary_dir:
		html_path = Path(temporary_dir) / "record.html"
		user_data_dir = Path(temporary_dir) / "browser-profile"
		html = record.html
		html = re.sub(r"charset\s*=\s*[\"']?windows-1251[\"']?", 'charset="utf-8"', html, flags=re.IGNORECASE)
		base_tag = f'<base href="{BASE_URL}/registers-doc-view/">'
		if "<head" in html.lower():
			html = re.sub(r"(<head[^>]*>)", r"\1" + base_tag, html, count=1, flags=re.IGNORECASE)
		else:
			html = base_tag + html
		html_path.write_text(html, encoding="utf-8")
		command = [
			browser,
			"--headless",
			"--disable-gpu",
			"--no-pdf-header-footer",
			f"--user-data-dir={user_data_dir}",
			f"--print-to-pdf={path.resolve()}",
			f"file:///{html_path.as_posix()}",
		]
		environment = os.environ.copy()
		environment["NO_PROXY"] = "new.fips.ru,fips.ru"
		subprocess.run(command, check=True, timeout=90, capture_output=True, env=environment, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
	return path


def find_browser() -> str:
	candidates = [
		os.environ.get("FIPS_BROWSER", ""),
		r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
		r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
		r"C:\Program Files\Google\Chrome\Application\chrome.exe",
		r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
	]
	for candidate in candidates:
		if candidate and Path(candidate).exists():
			return candidate
	raise FipsError("Не найден Microsoft Edge или Google Chrome для печати PDF.")


def parse_numbers(value: str) -> list[str]:
	numbers = [item.strip() for item in re.split(r"[\s,;]+", value) if item.strip()]
	invalid = [item for item in numbers if not item.isdigit()]
	if invalid:
		raise ValueError(f"Номера должны содержать только цифры: {', '.join(invalid)}")
	return list(dict.fromkeys(numbers))


class FipsApp:
	def __init__(self, root: Tk) -> None:
		self.root = root
		self.root.title("Патенты ФИПС -> PDF")
		self.root.geometry("720x520")
		self.root.minsize(620, 440)
		self.registry = StringVar(value=list(REGISTRIES)[0])
		self.output_dir = StringVar(value=str(Path.cwd() / "patents"))
		self._build_ui()

	def _build_ui(self) -> None:
		frame = Frame(self.root, padx=16, pady=14)
		frame.pack(fill=BOTH, expand=True)
		Label(frame, text="Реестр ФИПС", font=("Segoe UI", 11, "bold")).pack(anchor="w")
		ttk.Combobox(frame, textvariable=self.registry, values=list(REGISTRIES), state="readonly").pack(fill=X, pady=(5, 12))
		Label(frame, text="Номера патентов (через пробел, запятую или точку с запятой)").pack(anchor="w")
		self.numbers = Entry(frame)
		self.numbers.pack(fill=X, pady=(5, 12))
		Label(frame, text="Папка для PDF").pack(anchor="w")
		output_frame = Frame(frame)
		output_frame.pack(fill=X, pady=(5, 12))
		Entry(output_frame, textvariable=self.output_dir).pack(side=LEFT, fill=X, expand=True)
		Button(output_frame, text="Обзор...", command=self.choose_output).pack(side=RIGHT, padx=(8, 0))
		self.start_button = Button(frame, text="Найти и сохранить PDF", command=self.start)
		self.start_button.pack(anchor="w", pady=(0, 12))
		self.log = Listbox(frame, height=14)
		self.log.pack(fill=BOTH, expand=True)

	def choose_output(self) -> None:
		selected = filedialog.askdirectory(initialdir=self.output_dir.get())
		if selected:
			self.output_dir.set(selected)

	def start(self) -> None:
		try:
			numbers = parse_numbers(self.numbers.get())
			if not numbers:
				raise ValueError("Введите хотя бы один номер патента.")
		except ValueError as error:
			messagebox.showerror("Проверка данных", str(error))
			return
		self.start_button.config(state="disabled")
		self.log.delete(0, END)
		threading.Thread(target=self._run, args=(numbers,), daemon=True).start()

	def _run(self, numbers: list[str]) -> None:
		client = FipsClient()
		output_dir = Path(self.output_dir.get())
		success = 0
		for number in numbers:
			self.root.after(0, self._write_log, f"Поиск № {number}...")
			try:
				record = client.get_record(number, self.registry.get())
				path = save_record_as_pdf(record, output_dir)
				success += 1
				self.root.after(0, self._write_log, f"Сохранён: {path.name}")
			except (FipsError, OSError, requests.RequestException) as error:
				self.root.after(0, self._write_log, f"Ошибка № {number}: {error}")
		self.root.after(0, self._finished, success, len(numbers))

	def _write_log(self, message: str) -> None:
		self.log.insert(END, message)
		self.log.see(END)

	def _finished(self, success: int, total: int) -> None:
		self.start_button.config(state="normal")
		messagebox.showinfo("Готово", f"Сохранено документов: {success} из {total}")


def cli_main(arguments: argparse.Namespace) -> int:
	client = FipsClient()
	output_dir = Path(arguments.output)
	for number in parse_numbers(arguments.numbers):
		record = client.get_record(number, arguments.registry)
		print(save_record_as_pdf(record, output_dir))
	return 0


def main() -> int:
	parser = argparse.ArgumentParser(description="Поиск патентов в открытых реестрах ФИПС и сохранение в PDF")
	parser.add_argument("--cli", action="store_true", help="запустить без GUI")
	parser.add_argument("--registry", choices=list(REGISTRIES), default="Изобретения")
	parser.add_argument("--numbers", help="номера через пробел или запятую")
	parser.add_argument("--output", default="patents")
	arguments = parser.parse_args()
	if arguments.cli:
		if not arguments.numbers:
			parser.error("для --cli требуется --numbers")
		try:
			return cli_main(arguments)
		except (FipsError, ValueError, OSError, requests.RequestException) as error:
			print(f"Ошибка: {error}", file=sys.stderr)
			return 1
	root = Tk()
	FipsApp(root)
	root.mainloop()
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
