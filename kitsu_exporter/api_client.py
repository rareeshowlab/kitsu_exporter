import gazu
import os

class KitsuClient:
    def __init__(self, host=None, ssl_verify=False):
        self.ssl_verify = ssl_verify
        if host:
            self.set_host(host)

    def set_host(self, host):
        # URL 보정: 프로토콜 자동 추가
        if not host.startswith(("http://", "https://")):
            host = "https://" + host
        
        # URL 보정: /api 접미사 자동 추가
        if not host.endswith("/api") and not host.endswith("/api/"):
            host = host.rstrip("/") + "/api"
            
        gazu.set_host(host)
        
        # SSL 검증 비활성화 설정 (gazu 내부 client 접근)
        if not self.ssl_verify:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            # gazu는 내부적으로 전역 client를 사용하므로 직접 속성을 수정할 수 있는지 확인 필요
            # 보통 gazu.client.get_client()로 접근 가능
            try:
                client = gazu.client.get_client()
                client.verify = False  # ssl_verify가 아니라 verify입니다.
            except:
                pass

    def login(self, email, password):
        try:
            gazu.log_in(email, password)
            return True, "Login Successful"
        except Exception as e:
            error_msg = str(e)
            # 상세 오류 분석 및 사용자 친화적 메시지
            if "SSLCertVerificationError" in error_msg or "certificate verify failed" in error_msg:
                error_msg = "SSL Certificate Verification Failed. Try checking 'Skip SSL Verification'."
            elif "ConnectionError" in error_msg:
                error_msg = "Could not connect to server. Check your URL and internet connection."
            
            print(f"Login failed: {error_msg}")
            return False, error_msg

    def get_projects(self):
        """모든 프로젝트 목록을 반환합니다."""
        return gazu.project.all_projects()

    def get_project_by_name(self, name):
        """이름으로 프로젝트를 찾습니다."""
        return gazu.project.get_project_by_name(name)

    def get_shots_for_project(self, project):
        """프로젝트의 모든 샷 정보를 가져옵니다."""
        return gazu.shot.all_shots_for_project(project)

    def get_tasks_for_shot(self, shot):
        """샷의 모든 태스크 정보를 가져옵니다."""
        return gazu.task.all_tasks_for_shot(shot)

    def get_task_status(self, task):
        """태스크의 현재 상태 정보를 가져옵니다."""
        # task["task_status_id"]를 통해 상태 정보를 조회하거나 이미 포함되어 있는지 확인
        return gazu.task.get_task_status(task["task_status_id"]) if "task_status_id" in task else None

    def get_thumbnail_url(self, entity):
        """샷 또는 태스크의 썸네일 ID(preview_file_id)를 가져옵니다."""
        try:
            name = entity.get("name", "Unknown")
            # 1. 엔티티 데이터에 이미 포함되어 있는지 확인
            preview_id = entity.get("preview_file_id")
            if preview_id:
                print(f"DEBUG: Found preview_id {preview_id} directly in entity {name}")
                return preview_id
            
            # 2. 포함되어 있지 않다면 전용 함수로 조회 시도
            print(f"DEBUG: No direct preview_id for {name}, searching via gazu.files...")
            preview_file = gazu.files.get_preview_file_by_entity(entity)
            if preview_file:
                preview_id = preview_file.get("id")
                print(f"DEBUG: Found preview_id {preview_id} via get_preview_file_by_entity for {name}")
                return preview_id
                
            print(f"DEBUG: Absolutely no preview_id found for {name}")
            return None
        except Exception as e:
            print(f"DEBUG: Failed to get preview_id for {entity.get('name')}: {e}")
            return None

    def get_all_shot_data(self, project_id):
        """특정 프로젝트의 모든 샷, 태스크, 상태 정보를 통합하여 반환합니다."""
        try:
            project = gazu.project.get_project(project_id)
            if not project:
                return []
                
            shots = gazu.shot.all_shots_for_project(project)
            
            # 상태 및 타입 리스트 미리 가져오기 (캐싱 용도)
            task_statuses = {ts["id"]: ts["name"] for ts in gazu.task.all_task_statuses() if isinstance(ts, dict)}
            task_types = {tt["id"]: tt["name"] for tt in gazu.task.all_task_types() if isinstance(tt, dict)}

            all_data = []
            for shot in shots:
                # shot이 딕셔너리가 아닌 ID 문자열인 경우 상세 정보 가져오기
                if isinstance(shot, str):
                    shot = gazu.shot.get_shot(shot)
                
                if not isinstance(shot, dict):
                    continue

                tasks = gazu.task.all_tasks_for_shot(shot)
                shot_info = {
                    "id": shot.get("id", ""),
                    "name": shot.get("name", "Unknown"),
                    "sequence": shot.get("sequence_name", ""),
                    "description": shot.get("description", ""),
                    "nb_frames": shot.get("nb_frames", ""),
                    "tasks": []
                }
                
                # 썸네일 정보
                shot_info["thumbnail_url"] = self.get_thumbnail_url(shot)

                if isinstance(tasks, list):
                    for task in tasks:
                        # task가 딕셔rer리가 아닌 ID 문자열인 경우 상세 정보 가져오기
                        if isinstance(task, str):
                            task = gazu.task.get_task(task)
                        
                        if not isinstance(task, dict):
                            continue

                        status_id = task.get("task_status_id")
                        type_id = task.get("task_type_id")
                        
                        status_name = task_statuses.get(status_id, "Unknown")
                        type_name = task_types.get(type_id, "Unknown")
                        
                        # 담당자 정보 안전하게 추출
                        assignees = []
                        task_assignees = task.get("assignees", [])
                        if isinstance(task_assignees, list):
                            for a in task_assignees:
                                if isinstance(a, dict):
                                    assignees.append(a.get("first_name", "Unknown"))
                                elif isinstance(a, str):
                                    # ID인 경우 이름 추출 시도 (성능상 생략하거나 간단히 처리)
                                    assignees.append("User")

                        shot_info["tasks"].append({
                            "type": type_name,
                            "status": status_name,
                            "assignees": assignees
                        })
                
                all_data.append(shot_info)
                
            return all_data
        except Exception as e:
            print(f"Error in get_all_shot_data: {e}")
            return []
