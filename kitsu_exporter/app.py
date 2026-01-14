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
    def compose(self) -> ComposeResult:
        yield Vertical(
            Label(f"Exporting: {self.app.selected_project['name']}", id="title"),
            Label("Initializing...", id="status_label"),
            Button("Start Export", variant="success", id="start_btn"),
            Button("Cancel", variant="error", id="cancel_btn"),
            id="export_container"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start_btn":
            self.query_one("#status_label").update("Fetching data from Kitsu...")
            self.run_worker(self.do_export(), thread=True)
            self.query_one("#start_btn").disabled = True
        elif event.button.id == "cancel_btn":
            self.app.pop_screen()

    async def do_export(self):
        project_id = self.app.selected_project["id"]
        # Step 1: Get Data
        shot_data = self.app.client.get_all_shot_data(project_id)
        
        self.query_one("#status_label").update("Generating Excel and downloading thumbnails...")
        
        # Step 2: Export
        # 사용자의 다운로드 폴더 경로 가져오기
        downloads_path = os.path.expanduser("~/Downloads")
        file_name = f"{self.app.selected_project['name']}_shots.xlsx"
        output_name = os.path.join(downloads_path, file_name)
        
        exporter = ExcelExporter(output_name)
        exporter.export_shots(shot_data)
        
        self.query_one("#status_label").update(f"Export Completed: {file_name}")
        self.app.notify(f"Saved to Downloads: {file_name}")
        print(f"DEBUG: File saved to {output_name}")
        self.query_one("#start_btn").disabled = False

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
        height: 10;
        margin-bottom: 1;
        border: solid green;
    }
    Button {
        width: 100%;
        margin-top: 1;
    }
    """
    
    def on_mount(self) -> None:
        self.push_screen(LoginScreen())

def main():
    app = KitsuExporterApp()
    app.run()

if __name__ == "__main__":
    main()
