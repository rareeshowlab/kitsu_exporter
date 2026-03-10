from textual.app import App, ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Header, Footer, Input, Button, Static, ListView, ListItem, Label, DirectoryTree, Checkbox
from textual.screen import Screen
from textual.worker import Worker, WorkerState
import os
import json
from pathlib import Path

from kitsu_exporter.api_client import KitsuClient
from kitsu_exporter.exporter import ExcelExporter

# 설정 파일 경로 (사용자 홈 디렉토리의 .kitsu_exporter_config.json)
CONFIG_FILE = Path.home() / ".kitsu_exporter_config.json"

class LoginScreen(Screen):
    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Kitsu Login", id="title"),
            Input(placeholder="Server URL (e.g. kitsu.example.com)", id="host"),
            Input(placeholder="Email", id="email"),
            Input(placeholder="Password", password=True, id="password"),
            Horizontal(
                Checkbox("Remember Me", value=True, id="remember_me"),
                id="remember_container"
            ),
            Button("Login", variant="primary", id="login_btn"),
            id="login_container"
        )

    def on_mount(self) -> None:
        """저장된 설정이 있으면 불러옵니다."""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    config = json.load(f)
                    self.query_one("#host").value = config.get("host", "")
                    self.query_one("#email").value = config.get("email", "")
                    self.query_one("#password").value = config.get("password", "")
                    
                    # 모든 정보가 있으면 자동 로그인 시도
                    if all([config.get("host"), config.get("email"), config.get("password")]):
                        self.app.call_after_refresh(self.perform_login)
            except Exception as e:
                print(f"DEBUG: Failed to load config: {e}")

    def perform_login(self) -> None:
        """자동 또는 버튼 클릭 시 로그인을 수행합니다."""
        host = self.query_one("#host").value
        email = self.query_one("#email").value
        password = self.query_one("#password").value
        remember = self.query_one("#remember_me").value

        if not all([host, email, password]):
            return

        self.app.client = KitsuClient(host, ssl_verify=False)
        success, message = self.app.client.login(email, password)
        
        if success:
            if remember:
                self.save_config(host, email, password)
            elif CONFIG_FILE.exists():
                os.remove(CONFIG_FILE) # 기억 안 함 선택 시 기존 파일 삭제
            
            self.app.push_screen(ProjectSelectScreen())
        else:
            self.app.notify(f"Login Failed: {message}", severity="error")

    def save_config(self, host, email, password):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump({"host": host, "email": email, "password": password}, f)
        except Exception as e:
            print(f"DEBUG: Failed to save config: {e}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "login_btn":
            self.perform_login()

class ProjectSelectScreen(Screen):
    def on_mount(self) -> None:
        self.load_projects()

    def load_projects(self):
        projects = self.app.client.get_projects()
        list_view = self.query_one(ListView)
        for p in projects:
            item = ListItem(Label(p["name"]))
            item.project_data = p
            list_view.append(item)

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Select Project", id="title"),
            ListView(id="project_list"),
            Button("Logout", id="logout_btn", variant="error"),
            id="project_container"
        )

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        project = event.item.project_data
        self.app.selected_project = project
        self.app.push_screen(ExportScreen())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "logout_btn":
            # 저장된 로그인 정보 삭제
            if CONFIG_FILE.exists():
                os.remove(CONFIG_FILE)
            self.app.notify("Logged out and credentials cleared.")
            self.app.pop_screen()

class ExportScreen(Screen):
    def on_mount(self) -> None:
        self.all_shot_data = []
        self.filtered_data = []
        # 버튼을 임시 비활성화하고 데이터를 먼저 불러옴
        self.query_one("#start_btn").disabled = True
        try:
            self.query_one("#export_artist_btn").disabled = True
        except:
            pass
        self.query_one("#search_btn").disabled = True
        self.query_one("#status_label").update("Fetching data from Kitsu (may take a moment)...")
        self.run_worker(self.fetch_data(), thread=True)

    async def fetch_data(self):
        project_id = self.app.selected_project["id"]
        # 워커 쓰레드 내부에서 동기 API 호출
        data = self.app.client.get_all_shot_data(project_id)
        # 데이터를 받아오면 메인 쓰레드 UI 업데이트
        self.app.call_from_thread(self.on_data_fetched, data)

    def on_data_fetched(self, data):
        self.all_shot_data = data
        self.filtered_data = data
        self.query_one("#start_btn").disabled = False
        try:
            self.query_one("#export_artist_btn").disabled = False
        except:
            pass
        self.query_one("#search_btn").disabled = False
        self.query_one("#status_label").update(f"Loaded {len(self.all_shot_data)} shots. Ready.")
        self.update_result_view()

    def update_result_view(self):
        list_view = self.query_one("#result_list")
        list_view.clear()
        for shot in self.filtered_data:
            seq = shot.get("sequence") or "N/A"
            name = shot.get("name") or "Unknown"
            
            task_info_list = []
            for task in shot.get("tasks", []):
                t_type = task.get("type", "Unknown")
                t_status = task.get("status", "Unknown")
                assignees = task.get("assignees", [])
                assignees_str = ", ".join(assignees) if assignees else "Unassigned"
                task_info_list.append(f"{t_type}({t_status}): {assignees_str}")
            
            task_info_text = ", ".join(task_info_list)
            if task_info_text:
                display_text = f"[{seq}] {name} - {task_info_text}"
            else:
                display_text = f"[{seq}] {name}"
                
            list_view.append(ListItem(Label(display_text)))

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label(f"Exporting: {self.app.selected_project['name']}", id="title"),
            Horizontal(
                Input(placeholder="Search by Shot Name or Sequence...", id="search_input"),
                Button("Search", id="search_btn", variant="primary"),
                id="search_container"
            ),
            ListView(id="result_list"),
            Label("Initializing...", id="status_label"),
            Horizontal(
                Button("Export", variant="success", id="start_btn"),
                Button("Export by Artist", variant="warning", id="export_artist_btn"),
                Button("Cancel", variant="error", id="cancel_btn"),
                id="action_container"
            ),
            id="export_container"
        )

    def apply_filter(self):
        search_query = self.query_one("#search_input").value.strip()
        if not search_query:
            self.filtered_data = self.all_shot_data
            self.update_result_view()
            self.query_one("#status_label").update(f"Showing all {len(self.filtered_data)} shots.")
            return

        import re
        pattern = r'(\w+)\[([^\]]*)\]=(?:\[([^\]]+)\]|"([^"]+)"|([^\s]+))'
        
        advanced_filters = []
        for m in re.finditer(pattern, search_query):
            key = m.group(1).lower()
            subkey = m.group(2).lower()
            val = m.group(3) or m.group(4) or m.group(5)
            val = val.lower()
            advanced_filters.append((key, subkey, val))
        
        simple_text = re.sub(pattern, '', search_query).strip().lower()
        simple_keywords = [k for k in simple_text.split() if k]
        
        filtered = []
        for shot in self.all_shot_data:
            passed = True
            
            for key, subkey, val in advanced_filters:
                filter_passed = False
                if key == "assignedto":
                    for task in shot.get("tasks", []):
                        if not subkey or task.get("type", "").lower() == subkey:
                            assignees = [str(a).lower() for a in task.get("assignees", [])]
                            if any(val in a for a in assignees):
                                filter_passed = True
                                break
                
                if not filter_passed:
                    passed = False
                    break
            
            if passed and simple_keywords:
                name = str(shot.get("name") or "").lower()
                seq = str(shot.get("sequence") or "").lower()
                
                # 모든 태스크의 담당자 이름(assignees) 추출 및 합치기
                assignees_text = " ".join([
                    str(a).lower() 
                    for task in shot.get("tasks", []) 
                    for a in task.get("assignees", [])
                ])
                
                for keyword in simple_keywords:
                    if keyword not in name and keyword not in seq and keyword not in assignees_text:
                        passed = False
                        break
                        
            if passed:
                filtered.append(shot)
        
        self.filtered_data = filtered
        self.update_result_view()
        self.query_one("#status_label").update(f"Found {len(self.filtered_data)} shots matching criteria.")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "search_btn":
            self.apply_filter()
        elif event.button.id == "start_btn":
            self.query_one("#status_label").update("Preparing export...")
            self.query_one("#start_btn").disabled = True
            try:
                self.query_one("#export_artist_btn").disabled = True
            except:
                pass
            self.query_one("#search_btn").disabled = True
            self.run_worker(self.do_export(), thread=True)
        elif event.button.id == "export_artist_btn":
            self.query_one("#status_label").update("Preparing artist exports...")
            self.query_one("#start_btn").disabled = True
            self.query_one("#export_artist_btn").disabled = True
            self.query_one("#search_btn").disabled = True
            self.run_worker(self.do_export_by_artist(), thread=True)
        elif event.button.id == "cancel_btn":
            self.app.pop_screen()

    async def do_export(self):
        if not self.filtered_data:
            self.app.call_from_thread(self.app.notify, "No data to export.", severity="error")
            self.app.call_from_thread(lambda: setattr(self.query_one("#start_btn"), "disabled", False))
            try:
                self.app.call_from_thread(lambda: setattr(self.query_one("#export_artist_btn"), "disabled", False))
            except:
                pass
            self.app.call_from_thread(lambda: setattr(self.query_one("#search_btn"), "disabled", False))
            return

        self.app.call_from_thread(self.query_one("#status_label").update, "Generating Excel and downloading thumbnails...")
        
        search_query = self.query_one("#search_input").value.strip()
        query_suffix = ""
        if search_query:
            import re
            # Clean up the query string to be safe for filenames
            safe_query = re.sub(r'[^a-zA-Z0-9]', '_', search_query)
            safe_query = re.sub(r'_+', '_', safe_query).strip('_')
            query_suffix = f"_{safe_query}" if safe_query else ""

        downloads_path = os.path.expanduser("~/Downloads")
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"{self.app.selected_project['name']}{query_suffix}_shots_{timestamp}.xlsx"
        output_name = os.path.join(downloads_path, file_name)
        
        exporter = ExcelExporter(output_name)
        exporter.export_shots(self.filtered_data)
        
        def on_complete():
            self.query_one("#status_label").update(f"Export Completed: {file_name}")
            self.app.notify(f"Saved to Downloads: {file_name}")
            self.query_one("#start_btn").disabled = False
            self.query_one("#search_btn").disabled = False
            try:
                self.query_one("#export_artist_btn").disabled = False
            except:
                pass
                
        self.app.call_from_thread(on_complete)

    async def do_export_by_artist(self):
        if not self.filtered_data:
            self.app.call_from_thread(self.app.notify, "No data to export.", severity="error")
            self.app.call_from_thread(lambda: setattr(self.query_one("#start_btn"), "disabled", False))
            self.app.call_from_thread(lambda: setattr(self.query_one("#export_artist_btn"), "disabled", False))
            self.app.call_from_thread(lambda: setattr(self.query_one("#search_btn"), "disabled", False))
            return

        artists = set()
        for shot in self.filtered_data:
            for task in shot.get("tasks", []):
                for a in task.get("assignees", []):
                    artists.add(str(a).strip())
                    
        if not artists:
            self.app.call_from_thread(self.app.notify, "No assigned artists found.", severity="warning")
            self.app.call_from_thread(lambda: setattr(self.query_one("#start_btn"), "disabled", False))
            self.app.call_from_thread(lambda: setattr(self.query_one("#export_artist_btn"), "disabled", False))
            self.app.call_from_thread(lambda: setattr(self.query_one("#search_btn"), "disabled", False))
            return

        downloads_path = os.path.expanduser("~/Downloads")
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        project_name = self.app.selected_project['name']
        
        exported_files = []
        for artist in artists:
            artist_shots = []
            for shot in self.filtered_data:
                assigned = False
                for task in shot.get("tasks", []):
                    if any(str(a).strip() == artist for a in task.get("assignees", [])):
                        assigned = True
                        break
                if assigned:
                    artist_shots.append(shot)
            
            if not artist_shots:
                continue
                
            safe_artist = "".join(c if c.isalnum() else "_" for c in artist).strip("_")
            file_name = f"{project_name}_{safe_artist}_{timestamp}.xlsx"
            output_name = os.path.join(downloads_path, file_name)
            
            self.app.call_from_thread(self.query_one("#status_label").update, f"Exporting for {artist}...")
            
            exporter = ExcelExporter(output_name)
            exporter.export_shots(artist_shots)
            exported_files.append(file_name)

        def on_multiple_complete():
            self.query_one("#status_label").update(f"Export Completed: {len(exported_files)} files exported.")
            self.app.notify(f"Saved {len(exported_files)} files to Downloads.", timeout=5.0)
            self.query_one("#start_btn").disabled = False
            self.query_one("#export_artist_btn").disabled = False
            self.query_one("#search_btn").disabled = False
            
        self.app.call_from_thread(on_multiple_complete)



class KitsuExporterApp(App):
    CSS = """
    #login_container, #project_container, #export_container {
        align: center middle;
        padding: 2;
    }
    #remember_container {
        height: auto;
        margin-bottom: 1;
        align: center middle;
    }
    #title {
        text-style: bold;
        margin-bottom: 1;
        text-align: center;
    }
    Input {
        margin-bottom: 1;
    }
    ListView {
        height: 1fr;
        min-height: 10;
        margin-bottom: 1;
        border: solid green;
    }
    Button {
        width: 100%;
        margin-top: 1;
    }
    #search_container {
        height: auto;
        align: left middle;
        margin-bottom: 1;
    }
    #action_container {
        height: auto;
        align: left middle;
    }
    #search_input {
        width: 1fr;
        margin-right: 1;
        margin-bottom: 0;
    }
    #search_btn {
        width: 15;
        margin-top: 0;
    }
    #action_container Button {
        margin-right: 1;
        width: 1fr;
    }
    """
    
    def on_mount(self) -> None:
        self.push_screen(LoginScreen())

def main():
    app = KitsuExporterApp()
    app.run()

if __name__ == "__main__":
    main()
