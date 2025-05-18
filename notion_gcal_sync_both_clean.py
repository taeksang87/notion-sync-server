import os
import json
import datetime
import requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# 설정
NOTION_TOKEN = "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"
DATABASE_ID = "1f2d34482a618030b943c6e8e257c566"
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"
NOTION_VERSION = "2022-06-28"
SCOPES = ["https://www.googleapis.com/auth/calendar"]
LOG_FILE = "sync_log.txt"

calendar_id_map = {
    "회사": "p7dots6jbg68456nu0pm9dauo8@group.calendar.google.com",
    "개인": "4694f3fb45e748dd27888296bba341fdfcc822b3764d1e1b282e0ade6d960957@group.calendar.google.com",
    "테니스": "16c8deb2d8b011876863bf13b7f873ae94f0ff608e3916344272a15a6f878ab8@group.calendar.google.com",
    "가족": "c6c868939cfbe5b52a67ce78497c71d04caf5bdd2423d8962b774f924a520ba5@group.calendar.google.com",
    "이벤트": "family02707576882357301625@group.calendar.google.com"
}

def log(msg):
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as log_fp:
        log_fp.write(msg + "\n")

def safe_select(prop, default="개인"):
    try:
        return prop["select"]["name"] if prop and "select" in prop else default
    except:
        return default

def safe_get_text(prop, key="rich_text", default=""):
    if prop is None:
        return default
    try:
        if isinstance(prop.get(key), list) and len(prop[key]) > 0:
            return prop[key][0].get("text", {}).get("content", default)
    except Exception as e:
        log(f"[경고] safe_get_text 예외: {e}")
    return default

def safe_get_select(property_value, field_name):
    """Notion select 타입의 값을 안전하게 가져오는 함수"""
    try:
        if not property_value or field_name not in property_value:
            return ""
        select_value = property_value[field_name]
        if not select_value:
            return ""
        return select_value.get("name", "")
    except Exception as e:
        log(f"⚠️ {field_name} 필드 읽기 실패: {e}")
        return ""

def get_google_service():
    try:
        log("🧪 get_google_service 진입")
        creds = None
        if os.path.exists(TOKEN_FILE):
            log("🔑 token.json 사용")
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        else:
            log("🔐 flow 시작")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
        log("✅ creds 생성 완료")
        return build("calendar", "v3", credentials=creds)
    except Exception as e:
        log(f"❌ get_google_service 예외 발생: {e}")
        raise

def get_notion_pages():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION
    }
    res = requests.post(url, headers=headers)
    return res.json().get("results", [])

def update_notion_event(page_id, event_id, html_link):
    """Notion 이벤트의 애플id와 URL을 업데이트하는 함수"""
    try:
        response = requests.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers={
                "Authorization": f"Bearer {NOTION_TOKEN}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json"
            },
            data=json.dumps({
                "properties": {
                    "애플id": {"rich_text": [{"text": {"content": event_id}}]},
                    "URL": {"url": html_link}
                }
            })
        )
        
        if response.status_code == 200:
            log(f"✅ Notion 이벤트 업데이트 완료 - ID: {event_id}")
            return True
        else:
            log(f"❌ Notion 이벤트 업데이트 실패: {response.text}")
            return False
            
    except Exception as e:
        log(f"❌ Notion 이벤트 업데이트 중 오류 발생: {e}")
        return False

def notion_to_google(service):
    notion_data = get_notion_pages()
    
    for page in notion_data:
        try:
            # select 타입의 값을 가져오는 방식 수정
            event_type = safe_get_select(page["properties"]["유형"], "select")
            if not event_type:
                log(f"⚠️ 유형이 지정되지 않은 이벤트 건너뛰기 - 제목: {safe_get_text(page['properties']['이름'], 'title', '')}")
                continue
                
            calendar_id = calendar_id_map.get(event_type)
            if not calendar_id:
                log(f"⚠️ 알 수 없는 캘린더 유형: {event_type}")
                continue
                
            log(f"📅 {event_type} 캘린더 처리 중...")
            
            # 필수 필드 검증
            title = safe_get_text(page["properties"]["이름"], "title", "")
            if not title:
                log(f"⚠️ 제목이 없는 이벤트 건너뛰기")
                continue
                
            start_time = page["properties"]["일시"]["date"]["start"]
            if not start_time:
                log(f"⚠️ 시작 시간이 없는 이벤트 건너뛰기: {title}")
                continue
            
            # 애플id가 이미 있는 경우 건너뛰기
            existing_event_id = safe_get_text(page["properties"].get("애플id", {}), "rich_text", "")
            if existing_event_id:
                log(f"⏭️ 이미 Google Calendar에 등록된 이벤트 건너뛰기: {title} (ID: {existing_event_id})")
                continue
            
            # 시간 형식 통일
            if isinstance(start_time, str):
                if 'T' not in start_time:  # 날짜만 있는 경우
                    start_time = f"{start_time}T00:00:00+09:00"
                elif not start_time.endswith('Z') and '+' not in start_time:
                    start_time = f"{start_time}+09:00"
                    
            end_time = page["properties"]["일시"]["date"]["end"]
            if not end_time:
                # 종료 시간이 없는 경우 시작 시간 + 1시간으로 설정
                if isinstance(start_time, str):
                    start_dt = datetime.datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    end_dt = start_dt + datetime.timedelta(hours=1)
                    end_time = end_dt.isoformat()
            
            # 이벤트 데이터 준비
            event = {
                'summary': title,
                'start': {'dateTime' if 'T' in start_time else 'date': start_time},
                'end': {'dateTime' if 'T' in end_time else 'date': end_time},
                'status': 'confirmed'
            }
            
            # Google Calendar에 이벤트 생성
            log(f"📤 Google Calendar에 새 일정 생성 중: {title}")
            created_event = service.events().insert(
                calendarId=calendar_id,
                body=event
            ).execute()
            
            if created_event and 'id' in created_event:
                # 생성된 이벤트의 ID와 URL을 Notion에 업데이트
                event_id = created_event['id']
                html_link = created_event.get('htmlLink', '')
                
                if update_notion_event(page["id"], event_id, html_link):
                    log(f"✅ 동기화 완료 - 제목: {title}")
                    log(f"  - Google Calendar ID: {event_id}")
                    log(f"  - URL: {html_link}")
                else:
                    log(f"⚠️ Google Calendar 등록은 완료되었으나 Notion 업데이트 실패 - 제목: {title}")
            else:
                log(f"❌ Google Calendar 이벤트 생성 실패 - 제목: {title}")
                
        except Exception as e:
            log(f"❌ Google Calendar 등록 실패: {e}")
            log(f"  - 이벤트 데이터: {json.dumps(event, ensure_ascii=False)}")
            continue

def google_to_notion(service):
    notion_data = get_notion_pages()
    notion_events = {}
    
    # 1. Notion 데이터 정리
    for page in notion_data:
        props = page["properties"]
        event_id = safe_get_text(props.get("애플id", {}), "rich_text", "")
        if event_id:
            notion_events[event_id] = page
            log(f"📋 Notion에 존재하는 이벤트 - ID: {event_id}, 제목: {safe_get_text(props['이름'], 'title', '')}")
    
    log(f"📊 Notion에 존재하는 이벤트 수: {len(notion_events)}개")
    
    # 2. 날짜 범위 설정 - 6개월 (timezone-aware)
    now = datetime.datetime.now(datetime.timezone.utc)
    today_start = datetime.datetime(now.year, now.month, now.day, tzinfo=datetime.timezone.utc)
    six_months_later = today_start + datetime.timedelta(days=180)
    
    log(f"📅 동기화 기간: {today_start.strftime('%Y-%m-%d')} ~ {six_months_later.strftime('%Y-%m-%d')}")
    
    for cal_name, cal_id in calendar_id_map.items():
        log(f"\n📅 {cal_name} 캘린더 동기화 시작")
        log(f"🔍 캘린더 ID: {cal_id}")
        
        try:
            # 캘린더 존재 여부 확인
            try:
                calendar = service.calendars().get(calendarId=cal_id).execute()
                log(f"✅ 캘린더 접근 가능: {calendar.get('summary', cal_name)}")
            except Exception as e:
                log(f"❌ 캘린더 접근 실패: {e}")
                continue
            
            # 이벤트 가져오기
            events = service.events().list(
                calendarId=cal_id,
                timeMin=today_start.isoformat(),
                timeMax=six_months_later.isoformat(),
                maxResults=100,
                singleEvents=True,
                orderBy="startTime"
            ).execute().get("items", [])
            
            log(f"📥 {cal_name} 캘린더에서 {len(events)}개의 이벤트 가져옴")
            
            # 이벤트 상세 로깅
            if len(events) > 0:
                log(f"📋 {cal_name} 캘린더 이벤트 목록:")
                for ev in events:
                    title = ev.get("summary", "(제목 없음)")
                    start = ev["start"].get("dateTime", ev["start"].get("date"))
                    event_id = ev["id"]
                    log(f"  - {title} (시작: {start}, ID: {event_id})")
            
            # 이벤트 처리 전에 중복 제거
            unique_events = {}
            for ev in events:
                title = ev.get('summary', '')
                start_time = ev['start'].get('dateTime', ev['start'].get('date'))
                event_id = ev['id']
                key = f"{title}_{start_time}"
                
                if key not in unique_events:
                    unique_events[key] = ev
                    log(f"📌 고유한 이벤트 추가: {title} (시작: {start_time}, ID: {event_id})")
                else:
                    log(f"⚠️ 중복 이벤트 발견: {title} (시작: {start_time}, ID: {event_id})")
            
            log(f"🔄 중복 제거 후 {len(unique_events)}개의 고유한 이벤트 남음")
            
            for ev in unique_events.values():
                google_event_id = ev["id"]
                title = ev.get("summary", "(제목 없음)")
                
                # Google Calendar ID로 중복 체크
                if google_event_id in notion_events:
                    log(f"⏭️ 이미 Notion에 존재하는 이벤트 건너뛰기 - 제목: {title}, ID: {google_event_id}")
                    continue
                
                # 시작 시간을 timezone-aware datetime으로 변환
                start_time = ev["start"].get("dateTime", ev["start"].get("date"))
                if isinstance(start_time, str):
                    if start_time.endswith('Z'):
                        start_time = datetime.datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    else:
                        start_time = datetime.datetime.fromisoformat(start_time)
                
                if isinstance(start_time, str) and 'T' not in start_time:
                    start_time = datetime.datetime.fromisoformat(start_time + 'T00:00:00+00:00')
                
                # 종료 시간도 같은 방식으로 처리
                end_time = ev["end"].get("dateTime", ev["end"].get("date"))
                if isinstance(end_time, str):
                    if end_time.endswith('Z'):
                        end_time = datetime.datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                    else:
                        end_time = datetime.datetime.fromisoformat(end_time)
                
                if isinstance(end_time, str) and 'T' not in end_time:
                    end_time = datetime.datetime.fromisoformat(end_time + 'T00:00:00+00:00')
                
                # 제목과 시작 시간으로 추가 중복 체크
                event_key = f"{title}_{start_time.isoformat()}"
                
                # Notion의 모든 이벤트를 검사하여 제목과 시작 시간이 같은 이벤트가 있는지 확인
                is_duplicate = False
                for existing_page in notion_data:
                    existing_title = safe_get_text(existing_page["properties"]["이름"], "title", "")
                    existing_start = existing_page["properties"]["일시"]["date"]["start"]
                    existing_id = safe_get_text(existing_page["properties"].get("애플id", {}), "rich_text", "")
                    
                    if isinstance(existing_start, str):
                        if existing_start.endswith('Z'):
                            existing_start = datetime.datetime.fromisoformat(existing_start.replace('Z', '+00:00'))
                        else:
                            existing_start = datetime.datetime.fromisoformat(existing_start)
                    
                    if existing_title == title and existing_start == start_time:
                        log(f"⚠️ 제목과 시작 시간이 같은 이벤트 발견 - 제목: {title}, 시작: {start_time}, 기존 ID: {existing_id}, 새 ID: {google_event_id}")
                        is_duplicate = True
                        break
                
                if is_duplicate:
                    log(f"⏭️ 중복 이벤트 건너뛰기 (제목/시간 중복) - 제목: {title}, ID: {google_event_id}")
                    continue
                
                # 새 이벤트 생성
                log(f"🔍 새 이벤트 생성 시도 - 제목: {title}, ID: {google_event_id}")
                try:
                    response = requests.post(
                        f"https://api.notion.com/v1/pages",
                        headers={
                            "Authorization": f"Bearer {NOTION_TOKEN}",
                            "Notion-Version": NOTION_VERSION,
                            "Content-Type": "application/json"
                        },
                        data=json.dumps({
                            "parent": {"database_id": DATABASE_ID},
                            "properties": {
                                "이름": {"title": [{"text": {"content": title}}]},
                                "일시": {"date": {"start": start_time.isoformat(), "end": end_time.isoformat()}},
                                "URL": {"url": ev.get("htmlLink", "")},
                                "유형": {"select": {"name": cal_name}},
                                "애플id": {"rich_text": [{"text": {"content": google_event_id}}]},
                                "상태": {"select": {"name": "등록"}}
                            }
                        })
                    )
                    
                    if response.status_code == 200:
                        log(f"✅ 새 이벤트 생성 완료 - 제목: {title}, ID: {google_event_id}")
                        notion_events[google_event_id] = response.json()
                    else:
                        log(f"❌ 이벤트 생성 실패 - 제목: {title}, ID: {google_event_id}, 오류: {response.text}")
                        
                except Exception as e:
                    log(f"❌ 이벤트 생성 중 오류 발생 - 제목: {title}, ID: {google_event_id}, 오류: {e}")
                    
        except Exception as e:
            log(f"❌ {cal_name} 캘린더 처리 중 오류 발생: {e}")
            continue
    
    log(f"\n📊 처리 완료 - Notion에 존재하는 총 이벤트 수: {len(notion_events)}개")

def main():
    try:
        log("🚀 통합 동기화 시작")
        service = get_google_service()
        notion_to_google(service)
        google_to_notion(service)
        log("✨ 동기화 완료")
    except Exception as e:
        log(f"❌ 동기화 중 오류 발생: {e}")

if __name__ == "__main__":
    main()