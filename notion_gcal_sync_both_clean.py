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

def notion_to_google(service):
    pages = get_notion_pages()
    log(f"📄 Notion 페이지 {len(pages)}개 확인됨")

    for page in pages:
        props = page["properties"]
        title = safe_get_text(props["이름"], "title", "(제목 없음)")
        log(f"🔍 처리 중인 이벤트: {title}")

        # 애플id가 공란인 경우 (Notion에서 작성된 새 일정)
        event_id = safe_get_text(props.get("애플id", {}), "rich_text", "")
        if not event_id:
            log(f"📝 Notion에서 작성된 새 일정 발견: {title}")
            
            # 상태 확인
            상태 = props["상태"]["select"]["name"] if props["상태"]["select"] else ""
            if 상태 != "등록":  # "등록" 상태인 경우만 처리
                log(f"⏭️ 상태 '{상태}'로 인해 건너뛰기: {title}")
                continue

            # Google Calendar에 등록
            유형 = safe_select(props.get("유형"), "개인")
            log(f"📁 유형: {유형}")
            cal_id = calendar_id_map.get(유형, calendar_id_map["개인"])
            
            start = props["일시"]["date"]["start"]
            end = props["일시"]["date"]["end"] or start
            
            try:
                # Google Calendar에 이벤트 생성
                log(f"📤 Google Calendar에 새 일정 생성 중: {title}")
                event = service.events().insert(
                    calendarId=cal_id,
                    body={
                        "summary": title,
                        "start": {"dateTime": start, "timeZone": "Asia/Seoul"},
                        "end": {"dateTime": end, "timeZone": "Asia/Seoul"}
                    }
                ).execute()
                
                # 생성된 이벤트의 ID와 URL만 Notion에 업데이트 (상태는 변경하지 않음)
                log(f"🔄 Notion에 Google Calendar 정보 업데이트 중: {title}")
                requests.patch(
                    f"https://api.notion.com/v1/pages/{page['id']}",
                    headers={
                        "Authorization": f"Bearer {NOTION_TOKEN}",
                        "Notion-Version": NOTION_VERSION,
                        "Content-Type": "application/json"
                    },
                    data=json.dumps({
                        "properties": {
                            "애플id": {"rich_text": [{"text": {"content": event["id"]}}]},
                            "URL": {"url": event.get("htmlLink", "")}
                            # 상태는 변경하지 않음 - "등록" 상태 유지
                        }
                    })
                )
                log(f"✅ Google Calendar 등록 및 Notion 업데이트 완료: {title}")
                
            except Exception as e:
                log(f"❌ Google Calendar 등록 실패: {e}")
                continue

        # 기존 로직 (애플id가 있는 경우의 처리)
        else:
            상태 = props["상태"]["select"]["name"] if props["상태"]["select"] else ""
            if 상태 not in ["등록", "수정"]:
                continue

            유형 = safe_select(props.get("유형"), "개인")
            cal_id = calendar_id_map.get(유형, calendar_id_map["개인"])
            start = props["일시"]["date"]["start"]
            end = props["일시"]["date"]["end"] or start
            page_id = page["id"]

            if 상태 == "등록":
                log(f"📤 Google 일정 생성 중: {title} ({유형})")
                try:
                    event = service.events().insert(
                        calendarId=cal_id,
                        body={
                            "summary": title,
                            "start": {"dateTime": start, "timeZone": "Asia/Seoul"},
                            "end": {"dateTime": end, "timeZone": "Asia/Seoul"}
                        }
                    ).execute()
                    
                    # 애플id와 URL만 업데이트하고 상태는 변경하지 않음
                    requests.patch(
                        f"https://api.notion.com/v1/pages/{page_id}",
                        headers={
                            "Authorization": f"Bearer {NOTION_TOKEN}",
                            "Notion-Version": NOTION_VERSION,
                            "Content-Type": "application/json"
                        },
                        data=json.dumps({
                            "properties": {
                                "애플id": {"rich_text": [{"text": {"content": event["id"]}}]},
                                "URL": {"url": event.get("htmlLink", "")}
                                # 상태는 변경하지 않음 - "등록" 상태 유지
                            }
                        })
                    )
                    log("✅ Google 일정 생성 완료")
                except Exception as e:
                    log(f"❌ Google 일정 생성 실패: {e}")
                    
            elif 상태 == "수정" and event_id:
                log(f"🔧 Google 일정 수정 중: {title}")
                try:
                    event = service.events().get(calendarId=cal_id, eventId=event_id).execute()
                    event["summary"] = title
                    event["start"]["dateTime"] = start
                    event["end"]["dateTime"] = end
                    service.events().update(calendarId=cal_id, eventId=event_id, body=event).execute()
                    log("✅ Google 일정 수정 완료")
                except Exception as e:
                    log(f"❌ Google 일정 수정 실패: {e}")

def google_to_notion(service):
    notion_data = get_notion_pages()
    notion_events = {}  # Google Calendar event ID를 키로 하는 딕셔너리
    
    # Notion 데이터 정리 - 이미 존재하는 이벤트 ID 수집
    for page in notion_data:
        props = page["properties"]
        event_id = safe_get_text(props.get("애플id", {}))
        if event_id:
            notion_events[event_id] = page
            log(f"📋 Notion에 이미 존재하는 이벤트 ID: {event_id} (제목: {props['이름']['title'][0]['text']['content']})")
    
    log(f"📊 Notion에 이미 존재하는 이벤트 수: {len(notion_events)}개")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    # 먼저 모든 Google Calendar 이벤트를 수집
    all_google_events = {}  # 캘린더별 Google 이벤트 저장
    for cal_name, cal_id in calendar_id_map.items():
        log(f"📅 {cal_name} 캘린더 이벤트 수집 중...")
        
        events = service.events().list(
            calendarId=cal_id,
            timeMin=now,
            maxResults=100,
            singleEvents=True,
            orderBy="startTime"
        ).execute().get("items", [])
        
        all_google_events[cal_id] = events
        log(f"📥 {cal_name} 캘린더에서 {len(events)}개의 이벤트 수집 완료")
    
    # 수집된 Google 이벤트를 Notion에 등록
    for cal_name, cal_id in calendar_id_map.items():
        log(f"📅 {cal_name} 캘린더 동기화 시작")
        
        for ev in all_google_events[cal_id]:
            google_event_id = ev["id"]
            title = ev.get("summary", "(제목 없음)")
            
            # 이미 Notion에 있는 이벤트는 건너뛰기
            if google_event_id in notion_events:
                log(f"⏭️ 중복 이벤트 건너뛰기: {title} (ID: {google_event_id})")
                continue
                
            log(f"🔍 새 이벤트 발견: {title} (ID: {google_event_id})")
            start = ev["start"].get("dateTime", ev["start"].get("date"))
            end = ev["end"].get("dateTime", ev["end"].get("date"))
            link = ev.get("htmlLink", "")
            
            # 새 이벤트 생성 - 반드시 "등록" 상태로
            log(f"📝 Google → Notion 새 이벤트 생성 시도: {title}")
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
                            "일시": {"date": {"start": start, "end": end}},
                            "URL": {"url": link},
                            "유형": {"select": {"name": cal_name}},
                            "애플id": {"rich_text": [{"text": {"content": google_event_id}}]},
                            "상태": {"select": {"name": "등록"}}  # 새 이벤트는 반드시 "등록" 상태로
                        }
                    })
                )
                if response.status_code == 200:
                    log("✅ Notion 새 이벤트 생성 완료 (상태: 등록)")
                    # 생성된 이벤트를 notion_events에 추가
                    notion_events[google_event_id] = response.json()
                else:
                    log(f"❌ Notion 새 이벤트 생성 실패: {response.text}")
            except Exception as e:
                log(f"❌ Notion 새 이벤트 생성 실패: {e}")
    
    # 마지막으로 Google Calendar에 없는 이벤트 처리
    all_google_ids = set()
    for events in all_google_events.values():
        all_google_ids.update(ev["id"] for ev in events)
    
    for notion_event_id, notion_page in notion_events.items():
        if notion_event_id not in all_google_ids:
            log(f"🗑️ Google Calendar에서 삭제된 이벤트 처리: {notion_page['properties']['이름']['title'][0]['text']['content']}")
            try:
                requests.patch(
                    f"https://api.notion.com/v1/pages/{notion_page['id']}",
                    headers={
                        "Authorization": f"Bearer {NOTION_TOKEN}",
                        "Notion-Version": NOTION_VERSION,
                        "Content-Type": "application/json"
                    },
                    data=json.dumps({
                        "properties": {
                            "상태": {"select": {"name": "삭제됨"}}
                        }
                    })
                )
                log("✅ 삭제된 이벤트 상태 업데이트 완료")
            except Exception as e:
                log(f"❌ 삭제된 이벤트 상태 업데이트 실패: {e}")

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