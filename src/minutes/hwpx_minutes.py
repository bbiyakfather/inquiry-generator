# -*- coding: utf-8 -*-
"""HWPX 회의록 생성 엔진 — COM 불필요, ElementTree + zipfile 직접 편집.

양식: templates/회의록_양식.hwpx  (7행×3열 표, [내비온] 회의록 양식)
  row 1 col 1: 사업명
  row 2 col 1: 일시
  row 3 col 1: 장소
  row 4 col 1: 회의주제
  row 5 col 1: 참석자 (다중줄), col 2: 총인원
  row 6 col 1: 회의내용 (sections + 사진표 deepcopy 보존)

charPr ID 매핑 (원본 양식 기준):
  0  = 11pt 일반
  11 = 11pt bold (참석자 첫줄)
  12 = 11pt bold (■ 섹션 헤더)
  13 = 총인원 셀 전용
  14 = empty_small 전용

paraPr ID 매핑:
  11 = 참석자 줄
  17 = header / empty_small
  20 = empty (일반 빈줄)
  24 = bullet (1차 항목)
  25 = sub (2차 항목)
  26 = 총인원 셀 전용
  27 = 회의내용 trailing
  28 = 사진표 포함 문단 (deepcopy 보존)
"""
import copy
import os
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from src.paths import resource_path

TEMPLATE_MINUTES = resource_path("templates", "회의록_양식.hwpx")

# HWP/HWPML 네임스페이스
_NS = {
    'ha':        'http://www.hancom.co.kr/hwpml/2011/app',
    'hp':        'http://www.hancom.co.kr/hwpml/2011/paragraph',
    'hp10':      'http://www.hancom.co.kr/hwpml/2016/paragraph',
    'hs':        'http://www.hancom.co.kr/hwpml/2011/section',
    'hc':        'http://www.hancom.co.kr/hwpml/2011/core',
    'hh':        'http://www.hancom.co.kr/hwpml/2011/head',
    'hhs':       'http://www.hancom.co.kr/hwpml/2011/history',
    'hm':        'http://www.hancom.co.kr/hwpml/2011/master-page',
    'hpf':       'http://www.hancom.co.kr/schema/2011/hpf',
    'dc':        'http://purl.org/dc/elements/1.1/',
    'opf':       'http://www.idpf.org/2007/opf/',
    'ooxmlchart':'http://www.hancom.co.kr/hwpml/2016/ooxmlchart',
    'hwpunitchar':'http://www.hancom.co.kr/hwpml/2016/HwpUnitChar',
    'epub':      'http://www.idpf.org/2007/ops',
    'config':    'urn:oasis:names:tc:opendocument:xmlns:config:1.0',
}
_HP = '{' + _NS['hp'] + '}'

for _prefix, _uri in _NS.items():
    ET.register_namespace(_prefix, _uri)


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _find_cell(tbl, row, col):
    for tr in tbl.findall(f'{_HP}tr'):
        for tc in tr.findall(f'{_HP}tc'):
            addr = tc.find(f'{_HP}cellAddr')
            if (addr is not None
                    and addr.attrib.get('rowAddr') == str(row)
                    and addr.attrib.get('colAddr') == str(col)):
                return tc
    return None


def _set_simple_cell_text(tbl, row, col, text):
    tc = _find_cell(tbl, row, col)
    if tc is None:
        return
    sublist = tc.find(f'{_HP}subList')
    p = sublist.find(f'{_HP}p')
    run = p.find(f'{_HP}run')
    t = run.find(f'{_HP}t')
    if t is None:
        t = ET.SubElement(run, f'{_HP}t')
    t.text = text
    for extra_run in p.findall(f'{_HP}run')[1:]:
        p.remove(extra_run)


def _make_para(ptype, text, vertpos):
    """paragraph 엘리먼트 생성. (element, next_vertpos) 반환."""
    if ptype == "empty_small":
        p = ET.Element(f'{_HP}p', {
            'id': '0', 'paraPrIDRef': '17', 'styleIDRef': '0',
            'pageBreak': '0', 'columnBreak': '0', 'merged': '0',
        })
        ET.SubElement(p, f'{_HP}run', {'charPrIDRef': '14'})
        lsa = ET.SubElement(p, f'{_HP}linesegarray')
        ET.SubElement(lsa, f'{_HP}lineseg', {
            'textpos': '0', 'vertpos': str(vertpos), 'vertsize': '500',
            'textheight': '500', 'baseline': '425', 'spacing': '300',
            'horzpos': '100', 'horzsize': '41204', 'flags': '393216',
        })
        return p, vertpos + 800

    elif ptype == "empty":
        p = ET.Element(f'{_HP}p', {
            'id': '0', 'paraPrIDRef': '20', 'styleIDRef': '0',
            'pageBreak': '0', 'columnBreak': '0', 'merged': '0',
        })
        ET.SubElement(p, f'{_HP}run', {'charPrIDRef': '0'})
        lsa = ET.SubElement(p, f'{_HP}linesegarray')
        ET.SubElement(lsa, f'{_HP}lineseg', {
            'textpos': '0', 'vertpos': str(vertpos), 'vertsize': '1100',
            'textheight': '1100', 'baseline': '935', 'spacing': '660',
            'horzpos': '100', 'horzsize': '41204', 'flags': '393216',
        })
        return p, vertpos + 1760

    elif ptype == "header":
        p = ET.Element(f'{_HP}p', {
            'id': '0', 'paraPrIDRef': '17', 'styleIDRef': '0',
            'pageBreak': '0', 'columnBreak': '0', 'merged': '0',
        })
        run = ET.SubElement(p, f'{_HP}run', {'charPrIDRef': '12'})
        ET.SubElement(run, f'{_HP}t').text = text
        lsa = ET.SubElement(p, f'{_HP}linesegarray')
        ET.SubElement(lsa, f'{_HP}lineseg', {
            'textpos': '0', 'vertpos': str(vertpos), 'vertsize': '1100',
            'textheight': '1100', 'baseline': '935', 'spacing': '660',
            'horzpos': '100', 'horzsize': '41204', 'flags': '393216',
        })
        return p, vertpos + 1760

    elif ptype == "bullet":
        p = ET.Element(f'{_HP}p', {
            'id': '0', 'paraPrIDRef': '24', 'styleIDRef': '0',
            'pageBreak': '0', 'columnBreak': '0', 'merged': '0',
        })
        run = ET.SubElement(p, f'{_HP}run', {'charPrIDRef': '0'})
        ET.SubElement(run, f'{_HP}t').text = text
        lsa = ET.SubElement(p, f'{_HP}linesegarray')
        ET.SubElement(lsa, f'{_HP}lineseg', {
            'textpos': '0', 'vertpos': str(vertpos), 'vertsize': '1100',
            'textheight': '1100', 'baseline': '935', 'spacing': '660',
            'horzpos': '500', 'horzsize': '40804', 'flags': '2490368',
        })
        return p, vertpos + 1760

    elif ptype == "sub":
        p = ET.Element(f'{_HP}p', {
            'id': '0', 'paraPrIDRef': '25', 'styleIDRef': '0',
            'pageBreak': '0', 'columnBreak': '0', 'merged': '0',
        })
        run = ET.SubElement(p, f'{_HP}run', {'charPrIDRef': '0'})
        ET.SubElement(run, f'{_HP}t').text = text
        lsa = ET.SubElement(p, f'{_HP}linesegarray')
        ET.SubElement(lsa, f'{_HP}lineseg', {
            'textpos': '0', 'vertpos': str(vertpos), 'vertsize': '1100',
            'textheight': '1100', 'baseline': '935', 'spacing': '660',
            'horzpos': '1000', 'horzsize': '40304', 'flags': '2490368',
        })
        return p, vertpos + 1760

    return None, vertpos


# ── 공개 API ─────────────────────────────────────────────────────────────────

def build_minutes(data: dict, template_hwpx: str = None, out_path: str = None) -> dict:
    """MINUTES_SCHEMA 데이터 → HWPX 파일 생성.

    data keys:
      business_name, meeting_date, meeting_place, meeting_topic,
      participants: [str, ...]  (첫 줄 bold, 나머지 일반),
      total_count: int,
      sections: [{"type": "header|bullet|sub|empty", "text": str}, ...]

    반환: {ok: bool, path: str, error?: str}
    """
    if template_hwpx is None:
        template_hwpx = TEMPLATE_MINUTES
    if not os.path.exists(template_hwpx):
        return {"ok": False, "error": f"템플릿 없음: {template_hwpx}"}

    tmp = tempfile.mkdtemp(prefix="minutes_")
    try:
        # 1) 압축 해제
        with zipfile.ZipFile(template_hwpx, 'r') as zf:
            zf.extractall(tmp)

        xml_path = os.path.join(tmp, "Contents", "section0.xml")
        tree = ET.parse(xml_path)
        root = tree.getroot()

        tbl = root.find(f'.//{_HP}tbl')
        if tbl is None:
            return {"ok": False, "error": "양식 표를 찾을 수 없습니다."}

        # 2) 단순 셀 (행1~4)
        _set_simple_cell_text(tbl, 1, 1, data.get("business_name", ""))
        _set_simple_cell_text(tbl, 2, 1, data.get("meeting_date", ""))
        _set_simple_cell_text(tbl, 3, 1, data.get("meeting_place", ""))
        _set_simple_cell_text(tbl, 4, 1, data.get("meeting_topic", ""))

        # 3) 참석자 셀 (행5 col1)
        participants = data.get("participants") or []
        tc5_1 = _find_cell(tbl, 5, 1)
        if tc5_1 is not None:
            sl5 = tc5_1.find(f'{_HP}subList')
            for old in sl5.findall(f'{_HP}p'):
                sl5.remove(old)
            for idx, line in enumerate(participants):
                p = ET.SubElement(sl5, f'{_HP}p', {
                    'id': '2147483648' if idx == 0 else '0',
                    'paraPrIDRef': '11', 'styleIDRef': '0',
                    'pageBreak': '0', 'columnBreak': '0', 'merged': '0',
                })
                char_id = '11' if idx == 0 else '0'
                run = ET.SubElement(p, f'{_HP}run', {'charPrIDRef': char_id})
                ET.SubElement(run, f'{_HP}t').text = line
                lsa = ET.SubElement(p, f'{_HP}linesegarray')
                ET.SubElement(lsa, f'{_HP}lineseg', {
                    'textpos': '0', 'vertpos': str(idx * 1760),
                    'vertsize': '1100', 'textheight': '1100',
                    'baseline': '935', 'spacing': '660',
                    'horzpos': '1000', 'horzsize': '31016', 'flags': '2490368',
                })

        # 4) 총인원 셀 (행5 col2)
        tc5_2 = _find_cell(tbl, 5, 2)
        if tc5_2 is not None:
            sl52 = tc5_2.find(f'{_HP}subList')
            for old in sl52.findall(f'{_HP}p'):
                sl52.remove(old)
            total = data.get("total_count", 0)
            count_text = f"(총 {total}명)" if total else ""
            p_cnt = ET.SubElement(sl52, f'{_HP}p', {
                'id': '0', 'paraPrIDRef': '26', 'styleIDRef': '0',
                'pageBreak': '0', 'columnBreak': '0', 'merged': '0',
            })
            run_cnt = ET.SubElement(p_cnt, f'{_HP}run', {'charPrIDRef': '13'})
            ET.SubElement(run_cnt, f'{_HP}t').text = count_text
            lsa_cnt = ET.SubElement(p_cnt, f'{_HP}linesegarray')
            ET.SubElement(lsa_cnt, f'{_HP}lineseg', {
                'textpos': '0', 'vertpos': '0', 'vertsize': '1100',
                'textheight': '1100', 'baseline': '935', 'spacing': '660',
                'horzpos': '1000', 'horzsize': '6112', 'flags': '393216',
            })

        # 5) 회의내용 셀 (행6 col1) — 사진표 deepcopy 보존
        tc6_1 = _find_cell(tbl, 6, 1)
        if tc6_1 is not None:
            sl6 = tc6_1.find(f'{_HP}subList')
            old_paras = sl6.findall(f'{_HP}p')

            photo_para = None
            for pp in old_paras:
                if (pp.attrib.get('paraPrIDRef') == '28'
                        or pp.find(f'.//{_HP}tbl') is not None):
                    photo_para = copy.deepcopy(pp)
                    break

            for old in list(sl6.findall(f'{_HP}p')):
                sl6.remove(old)

            vpos = 0
            p0, vpos = _make_para("empty_small", "", vpos)
            sl6.append(p0)

            sections = data.get("sections") or []
            for sec in sections:
                ptype = sec.get("type", "empty")
                text = sec.get("text", "")
                para, vpos = _make_para(ptype, text, vpos)
                if para is not None:
                    sl6.append(para)

            p_pre, vpos = _make_para("empty", "", vpos)
            sl6.append(p_pre)

            if photo_para is not None:
                photo_lsa = photo_para.find(f'{_HP}linesegarray')
                if photo_lsa is not None:
                    ls = photo_lsa.find(f'{_HP}lineseg')
                    if ls is not None:
                        ls.attrib['vertpos'] = str(vpos)
                sl6.append(photo_para)
                vpos += 2608

            p_trail = ET.Element(f'{_HP}p', {
                'id': '0', 'paraPrIDRef': '27', 'styleIDRef': '0',
                'pageBreak': '0', 'columnBreak': '0', 'merged': '0',
            })
            ET.SubElement(p_trail, f'{_HP}run', {'charPrIDRef': '0'})
            lsa_t = ET.SubElement(p_trail, f'{_HP}linesegarray')
            ET.SubElement(lsa_t, f'{_HP}lineseg', {
                'textpos': '0', 'vertpos': str(vpos), 'vertsize': '1100',
                'textheight': '1100', 'baseline': '935', 'spacing': '660',
                'horzpos': '1000', 'horzsize': '40304', 'flags': '393216',
            })
            sl6.append(p_trail)

        # 6) XML 기록
        xml_decl = '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
        xml_str = ET.tostring(root, encoding='unicode', xml_declaration=False)
        with open(xml_path, 'w', encoding='utf-8') as f:
            f.write(xml_decl + xml_str)

        # 7) PrvText.txt 업데이트
        prvtext_path = os.path.join(tmp, "Preview", "PrvText.txt")
        if os.path.exists(prvtext_path):
            lines = [
                "<회 의 록>",
                f"<사업명><{data.get('business_name', '')}>",
                f"<일  시><{data.get('meeting_date', '')}>",
                f"<장  소><{data.get('meeting_place', '')}>",
                f"<회의주제><{data.get('meeting_topic', '')}>",
                "<참석자><" + (participants[0] if participants else ""),
            ]
            if len(participants) > 1:
                lines.append("\n".join(participants[1:]) + f"><(총 {data.get('total_count', 0)}명)>")
            else:
                lines.append(f"><(총 {data.get('total_count', 0)}명)>")
            lines.append("<회의내용>")
            for sec in (data.get("sections") or []):
                lines.append(sec.get("text", "") if sec.get("type") != "empty" else "")
            with open(prvtext_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(lines) + "\n")

        # 8) HWPX 재패키징 (mimetype STORED 첫번째)
        if out_path is None:
            topic = data.get("meeting_topic", "회의록")[:20].replace(" ", "_")
            date_tag = (data.get("meeting_date") or "")[:10].replace(". ", "").replace(".", "")
            out_path = os.path.join(
                os.path.dirname(template_hwpx),
                f"회의록_{topic}_{date_tag}.hwpx",
            )

        if os.path.exists(out_path):
            os.remove(out_path)

        with zipfile.ZipFile(out_path, 'w') as zf:
            mime_src = os.path.join(tmp, "mimetype")
            if os.path.exists(mime_src):
                zf.write(mime_src, "mimetype", compress_type=zipfile.ZIP_STORED)
            for dirpath, _, filenames in os.walk(tmp):
                for fn in filenames:
                    if fn == "mimetype":
                        continue
                    full = os.path.join(dirpath, fn)
                    arc = os.path.relpath(full, tmp).replace("\\", "/")
                    zf.write(full, arc, compress_type=zipfile.ZIP_DEFLATED)

        return {"ok": True, "path": out_path}

    except Exception as e:
        import traceback
        return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
