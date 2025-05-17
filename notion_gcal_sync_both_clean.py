
with open("sync_log.txt", "w", encoding="utf-8") as log_fp:
    def log(msg):
        print(msg)
        log_fp.write(msg + "\n")


import os
import json
import datetime
import requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

LOG_FILE = "sync_log.txt"
    print(msg)
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

try:
    log("🚀 통합 동기화 시작")

    # 설정
    NOTION_TOKEN = "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"
    DATABASE_ID = "1f2d34482a618030b943c6e8e257c566"
    CREDENTIALS_FILE = "credentials.json"
    TOKEN_FILE = "token.json"
    NOTION_VERSION = "2022-06-28"
    SCOPES = ["https://www.googleapis.com/auth/calendar"]

    calendar_id_map = {
        "회사": "p7dots6jbg68456nu0pm9dauo8@group.calendar.google.com",
        "개인": "4694f3fb45e748dd27888296bba341fdfcc822b3764d1e1b282e0ade6d960957@group.calendar.google.com",
        "테니스": "16c8deb2d8b011876863bf13b7f873ae94f0ff608e3916344272a15a6f878ab8@group.calendar.google.com",
        "가족": "c6c868939cfbe5b52a67ce78497c71d04caf5bdd2423d8962b774f924a520ba5@group.calendar.google.com",
        "이벤트": "family02707576882357301625@group.calendar.google.com"
    }

    
def get_google_service():
    try:
        print("🧪 get_google_service 진입")
        creds = None
        if os.path.exists(TOKEN_FILE):
            print("🔑 token.json 사용")
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        else:
            print("🔐 flow 시작")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
        print("✅ creds 생성 완료")
        return build("calendar", "v3", credentials=creds)
    except Exception as e:
        print(f"❌ get_google_service 예외 발생: {e}")
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
    print(f"📄 Notion 페이지 {len(pages)}개 확인됨")

    for page in pages:
        props = page["properties"]
        title = safe_get_text(props["이름"], "title", "(제목 없음)")
        print(f"🔍 처리 중인 이벤트: {title}")

        상태 = props["상태"]["select"]["name"] if props["상태"]["select"] else ""
        print(f"📌 상태: {상태}")
        if 상태 not in ["등록", "수정"]:
            continue

        유형 = safe_select(props.get("유형"), "개인")
        print(f"📁 유형: {유형}")

        cal_id = calendar_id_map.get(유형, calendar_id_map["개인"])
        start = props["일시"]["date"]["start"]
        end = props["일시"]["date"]["end"] or start
        page_id = page["id"]
        event_id = safe_get_text(props["애플id"], "rich_text", "")

        if 상태 == "등록":
            print(f"📤 Google 일정 생성 중: {title} ({유형})")
            event = service.events().insert(calendarId=cal_id, body={
                "summary": title,
                "start": {"dateTime": start, "timeZone": "Asia/Seoul"},
                "end": {"dateTime": end, "timeZone": "Asia/Seoul"}
            }).execute()
            requests.patch(f"https://api.notion.com/v1/pages/{page_id}",
                headers={
                    "Authorization": f"Bearer {NOTION_TOKEN}",
                    "Notion-Version": NOTION_VERSION,
                    "Content-Type": "application/json"
                },
                data=json.dumps({
                    "properties": {
                        "애플id": {"rich_text": [{"text": {"content": event["id"]}}]},
                        "URL": {"url": event.get("htmlLink", "")},
                        "상태": {"select": {"name": "수정"}}
                    }
                }))
            print("✅ Google 일정 생성 완료")
        elif 상태 == "수정" and event_id:
            print(f"🔧 Google 일정 수정 중: {title}")
            try:
                event = service.events().get(calendarId=cal_id, eventId=event_id).execute()
                event["summary"] = title
                event["start"]["dateTime"] = start
                event["end"]["dateTime"] = end
                service.events().update(calendarId=cal_id, eventId=event_id, body=event).execute()
                print("✅ Google 일정 수정 완료")
            except Exception as e:
                print(f"❌ Google 일정 수정 실패: {e}")

            if 상태 == "등록":
                log(f"📤 [등록] Google 일정 생성 중: {title} ({cal_name})")
                event = service.events().insert(calendarId=cal_id, body={
                    "summary": title,
                    "start": {"dateTime": start, "timeZone": "Asia/Seoul"},
                    "end": {"dateTime": end, "timeZone": "Asia/Seoul"}
                }).execute()
                requests.patch(f"https://api.notion.com/v1/pages/{page_id}",
                    headers={
                        "Authorization": f"Bearer {NOTION_TOKEN}",
                        "Notion-Version": NOTION_VERSION,
                        "Content-Type": "application/json"
                    },
                    data=json.dumps({
                        "properties": {
                            "애플id": {"rich_text": [{"text": {"content": event["id"]}}]},
                            "URL": {"url": event.get("htmlLink", "")},
                            "상태": {"select": {"name": "수정"}}
                        }
                    }))
                log("✅ 생성 완료")
            elif 상태 == "수정" and event_id:
                log(f"🔧 [수정] Google 일정 업데이트 중: {title} ({cal_name})")
                try:
                    event = service.events().get(calendarId=cal_id, eventId=event_id).execute()
                    event["summary"] = title
                    event["start"]["dateTime"] = start
                    event["end"]["dateTime"] = end
                    service.events().update(calendarId=cal_id, eventId=event_id, body=event).execute()
                    log("✅ 수정 완료")
                except Exception as e:
                    log(f"❌ 수정 실패: {e}")

    def google_to_notion(service):
        notion_data = get_notion_pages()
        def find(gid):
            for row in notion_data:
                prop = row["properties"].get("애플id", {})
                event_id = safe_get_text(prop)
                if event_id == gid:
                    return row["id"]
            return None

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        for cname, cid in calendar_id_map.items():
            events = service.events().list(
                calendarId=cid, timeMin=now, maxResults=10,
                singleEvents=True, orderBy="startTime").execute().get("items", [])
            for ev in events:
                sid = ev["id"]
                title = ev.get("summary", "(No Title)")
                start = ev["start"].get("dateTime", ev["start"].get("date"))
                end = ev["end"].get("dateTime", ev["end"].get("date"))
                link = ev.get("htmlLink", "")
                match = find(sid)
                if match:
                    log(f"🔁 Google → Notion 수정: {title}")
                    requests.patch(f"https://api.notion.com/v1/pages/{match}",
                        headers={
                            "Authorization": f"Bearer {NOTION_TOKEN}",
                            "Notion-Version": NOTION_VERSION,
                            "Content-Type": "application/json"
                        },
                        data=json.dumps({
                            "properties": {
                                "이름": {"title": [{"text": {"content": title}}]},
                                "일시": {"date": {"start": start, "end": end}},
                                "유형": {"select": {"name": cname}},
                                "URL": {"url": link},
                                "상태": {"select": {"name": "수정"}}
                            }
                        }))
                else:
                    log(f"🆕 Google → Notion 생성: {title}")

                    res = requests.post("https://api.notion.com/v1/pages",
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
                                "애플id": {"rich_text": [{"text": {"content": sid}}]},
                                "유형": {"select": {"name": cname}},
                                "URL": {"url": link},
                                "상태": {"select": {"name": "등록"}}
                            }
                        }))
                    if res.status_code != 200:
                        log(f"❌ Notion 일정 생성 실패: {res.status_code} / {res.text}")
                    else:
                        log("✅ Notion 일정 생성 성공")
                                "유형": {"select": {"name": cname}},
                                "URL": {"url": link},
                                "상태": {"select": {"name": "등록"}}
                            }
                        }))

print("🔧 svc 생성 중...")
    svc = get_google_service()
print("✅ svc 생성 완료")
print("🚀 Notion → Google 시작")
    notion_to_google(svc)
print("✅ Notion → Google 완료")
print("🚀 Google → Notion 시작")
    google_to_notion(svc)
print("✅ Google → Notion 완료")
    log("✅ 모든 동기화 완료")

except Exception as e:
    log(f"❌ 최상위 오류: {e}")

log_fp.close()
input("\n[Enter] 누르면 종료됩니다...")