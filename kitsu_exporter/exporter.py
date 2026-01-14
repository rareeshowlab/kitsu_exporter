import pandas as pd
import requests
from openpyxl import Workbook
from openpyxl.drawing.image import Image
from openpyxl.utils import get_column_letter
import os
import tempfile
from io import BytesIO

class ExcelExporter:
    def __init__(self, output_path="output.xlsx"):
        self.output_path = output_path

    def export_shots(self, shot_data):
        """
        shot_data: list of dicts from KitsuClient.get_all_shot_data
        """
        # Flatten tasks for processing (if needed) or keep it structured.
        # 엑셀에서는 한 샷 당 여러 줄 혹은 한 줄에 여러 컬럼으로 태스크를 표시할 수 있음.
        # 여기서는 한 줄에 여러 컬럼(태스크 타입별로) 표시하는 방식을 취함.
        
        # 태스크 타입 종류 파악
        task_types = set()
        for shot in shot_data:
            for task in shot["tasks"]:
                task_types.add(task["type"])
        
        sorted_task_types = sorted(list(task_types))
        
        # 데이터프레임 구성을 위한 리스트 생성
        rows = []
        for shot in shot_data:
            row = {
                "Sequence": shot["sequence"],
                "Shot Name": shot["name"],
                "Description": shot["description"],
                "Nb Frames": shot["nb_frames"],
                "Thumbnail": shot["thumbnail_url"] # URL 보관
            }
            # 태스크 정보 추가
            for tt in sorted_task_types:
                # 해당 타입의 태스크 찾기 (보통 하나지만 여러 개일 수도 있음)
                task_status = ""
                for t in shot["tasks"]:
                    if t["type"] == tt:
                        task_status = t["status"]
                        break
                row[tt] = task_status
            rows.append(row)

        df = pd.DataFrame(rows)
        
        # Openpyxl을 사용하여 엑셀 작성 (이미지 삽입을 위해)
        wb = Workbook()
        ws = wb.active
        ws.title = "Shots"

        # 헤더 작성
        headers = ["Thumbnail", "Sequence", "Shot Name", "Description", "Nb Frames"] + sorted_task_types
        ws.append(headers)

        # 행 데이터 및 이미지 처리
        temp_files = [] # 저장 후 삭제할 임시 파일 목록
        
        for i, row in enumerate(rows, start=2):
            # 텍스트 데이터 먼저 삽입
            ws.cell(row=i, column=2, value=row["Sequence"])
            ws.cell(row=i, column=3, value=row["Shot Name"])
            ws.cell(row=i, column=4, value=row["Description"])
            ws.cell(row=i, column=5, value=row["Nb Frames"])
            for j, tt in enumerate(sorted_task_types, start=6):
                ws.cell(row=i, column=j, value=row[tt])

            # 썸네일 이미지 처리 (preview_file_id 사용)
            preview_id = row["Thumbnail"]
            if preview_id:
                try:
                    import gazu
                    import urllib3
                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

                    # Gazu 내부 클라이언트의 SSL 설정을 다시 한번 확정
                    try:
                        gazu.client.get_client().verify = False
                    except:
                        pass

                    # 임시 파일 생성
                    fd, tmp_path = tempfile.mkstemp(suffix=".png")
                    os.close(fd)
                    temp_files.append(tmp_path)
                    
                    try:
                        # Gazu 내장 함수로 고해상도 고정 이미지(Cover) 다운로드
                        # download_preview_file은 영상일 확률이 높으므로 커버를 우선 사용합니다.
                        print(f"DEBUG: Downloading high-quality cover for ID {preview_id}")
                        try:
                            # 1. 고화질 커버 시도 (영상의 대문 이미지 등)
                            gazu.files.download_preview_file_cover(preview_id, tmp_path)
                        except:
                            # 2. 실패 시 일반 썸네일 시도
                            print(f"DEBUG: Cover download failed, falling back to thumbnail for {row['Shot Name']}")
                            gazu.files.download_preview_file_thumbnail(preview_id, tmp_path)
                        
                        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                            try:
                                img = Image(tmp_path)
                                # 이미지 크기 대폭 확대 (가로 800px)
                                img.width = 800
                                img.height = 448
                                
                                # 셀 위치 설정 및 추가
                                cell_address = f"A{i}"
                                ws.add_image(img, cell_address)
                                ws.row_dimensions[i].height = 360
                                print(f"DEBUG: Image embedded successfully for {row['Shot Name']}")
                            except Exception as img_err:
                                print(f"DEBUG: Openpyxl image loading error: {img_err}")
                        else:
                            print(f"DEBUG: No valid image file obtained for {row['Shot Name']}")
                    except Exception as download_err:
                        print(f"DEBUG: Overall download process error: {download_err}")
                            
                except Exception as e:
                    print(f"DEBUG: Error processing shot {row['Shot Name']}: {e}")

        # 열 너비 조절
        ws.column_dimensions["A"].width = 110 # 확대된 이미지 너비에 맞춰 대폭 확장
        ws.column_dimensions["B"].width = 15
        ws.column_dimensions["C"].width = 15
        ws.column_dimensions["D"].width = 30 # Description
        ws.column_dimensions["E"].width = 10 # Nb Frames
        for j in range(6, len(headers) + 1):
            from openpyxl.utils import get_column_letter
            ws.column_dimensions[get_column_letter(j)].width = 12

        # 모든 이미지 처리가 끝난 후 엑셀 저장 (이 시점까지 임시 파일이 유지되어야 함)
        print(f"DEBUG: Saving workbook to Downloads: {self.output_path}")
        wb.save(self.output_path)
        
        # 저장 완료 후 임시 파일 일괄 삭제
        for f_path in temp_files:
            try:
                if os.path.exists(f_path):
                    os.remove(f_path)
            except:
                pass
                
        print(f"DEBUG: Export completed. File saved at {self.output_path}")
        return self.output_path
