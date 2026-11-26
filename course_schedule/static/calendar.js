document.addEventListener("DOMContentLoaded", () => {
  const el = document.getElementById("calendar");
  const isAdmin = el.dataset.admin === "1";

  const calendar = new FullCalendar.Calendar(el, {
    initialView: "timeGridWeek",
    locale: "zh-tw",
    firstDay: 1,
    slotMinTime: "08:00:00",
    slotMaxTime: "19:00:00",
    slotDuration: "00:30:00",
    expandRows: true,
    allDaySlot: false,
    height: "auto",
    editable: isAdmin,               // 只有管理員能拖曳
    eventDurationEditable: isAdmin,  // 只有管理員能拉伸時間
    events: "/schedule/events",
    eventDrop: handleChange,
    eventResize: handleChange,
    slotEventOverlap: false,         // 重疊的課程左右並排，不再互相蓋住
    eventMaxStack: 4,
    displayEventTime: false,         // 時間已在滑過／點擊提示裡，省出空間給課名
    eventDidMount: (info) => {       // 滑過顯示完整資訊
      info.el.title = info.event.extendedProps.tip;
    },
    eventClick: (info) => {          // 點擊顯示完整資訊
      alert(info.event.extendedProps.tip);
    },
    eventContent: (arg) => {         // 事件內容：課名、教室、老師（置中）
      const p = arg.event.extendedProps;
      const title = p.overlap ? `${p.code}<br>${p.name}` : `${p.code} ${p.name}`;
      return { html: `<div class="ev-box"><b>${title}</b>${p.room}<br>${p.teacher}</div>` };
    },
    eventsSet: (events) => {         // 標記哪些課程時間重疊
      events.forEach((a) => {
        const overlap = events.some((b) => b !== a && a.start < b.end && b.start < a.end);
        if (a.extendedProps.overlap !== overlap) {
          a.setExtendedProp("overlap", overlap);
        }
      });
    },
  });
  calendar.render();                 // 一定要有，否則不會畫出週曆

  // 管理員拖曳或拉伸後，把新時間存到後端
  async function handleChange(info) {
    try {
      const res = await fetch(`/schedule/sessions/${info.event.id}/move`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ start: info.event.startStr, end: info.event.endStr }),
      });
      if (!res.ok) throw new Error();
      const data = await res.json();
      if (data.conflict) alert("已儲存，但此時段與其他課程或借用衝突。");
    } catch (e) {
      alert("儲存失敗，已還原。");
      info.revert();                 // 失敗就彈回原位
    }
  }
});