"""
Word排版工具 - 党政机关公文格式 (GB/T 9704-2012)
功能：上传Word文档，自动按照公文规范排版后下载

排版规则：
  - 纸张: A4
  - 页边距: 上3.7cm 下3.5cm 左2.7cm 右2.7cm
  - 行距: 固定值28磅 (默认)
  - 每页22行，每行28字
  - 标题: 二号方正小标宋，居中
  - 一级标题(一、): 三号方正黑体
  - 二级标题(（一）): 三号方正楷体
  - 三级标题(1.): 三号方正仿宋
  - 四级标题(（1）): 三号方正仿宋
  - 正文: 三号方正仿宋，首行缩进2字符
  - 页码: 4号半角阿拉伯数字，底端外侧，左右一字线
"""

import io
import re
from docx import Document
from docx.shared import Pt, Cm, Inches, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml, OxmlElement
from flask import Blueprint, render_template, request, send_file, flash

format_bp = Blueprint('format', __name__, url_prefix='/format')

# ============================================================
# 公文排版默认配置（GB/T 9704-2012）
# ============================================================
DEFAULT_CONFIG = {
    # 纸张
    'page_width': 21.0,     # A4: 21cm
    'page_height': 29.7,    # A4: 29.7cm

    # 页边距 (cm)
    'margin_top': 3.7,
    'margin_bottom': 3.5,
    'margin_left': 2.7,
    'margin_right': 2.7,

    # 行距 (固定值, 磅)
    'line_spacing_fixed': 28,

    # 标题 (二号方正小标宋 = 22pt)
    'title_font': '方正小标宋体',
    'title_size': 22,
    'title_bold': False,

    # 一级标题 "一、" (三号方正黑体 = 16pt)
    'h1_font': '方正黑体体',
    'h1_size': 16,
    'h1_bold': False,

    # 二级标题 "（一）" (三号方正楷体)
    'h2_font': '方正楷体体',
    'h2_size': 16,
    'h2_bold': False,

    # 三/四级标题 "1." / "（1）" (三号方正仿宋)
    'h3_font': '方正仿宋体',
    'h3_size': 16,
    'h3_bold': False,
    'h4_font': '方正仿宋体',
    'h4_size': 16,
    'h4_bold': False,

    # 正文 (三号方正仿宋)
    'body_font': '方正仿宋体',
    'body_size': 16,

    # 首行缩进 (字符数)
    'first_line_indent': 2,

    # 页码
    'page_number_style': 'official',  # official = 公文样式 (4号, 底端外侧, 一字线)
    'page_number_font_size': 14,      # 4号 = 14pt

    # 版记 (4号方正仿宋 = 14pt)
    'footer_font': '方正仿宋体',
    'footer_size': 14,

    # 附件标记
    'attachment_label': True,
}

# 层级标题模式识别正则
LEVEL1_PATTERN = re.compile(r'^[一二三四五六七八九十]+[、．](?!\d)')   # 一、  二、
LEVEL2_PATTERN = re.compile(r'^（[一二三四五六七八九十]+）')          # （一）
LEVEL3_PATTERN = re.compile(r'^\d+\.[　 ]?')                         # 1.
LEVEL4_PATTERN = re.compile(r'^（\d+）')                             # （1）


class DocumentFormatter:
    """公文格式化器"""

    def __init__(self, doc, config=None):
        self.doc = doc
        self.config = config or DEFAULT_CONFIG.copy()

    def set_page_layout(self):
        """设置页面布局：A4 + 页边距"""
        section = self.doc.sections[0]
        section.page_width = Cm(self.config['page_width'])
        section.page_height = Cm(self.config['page_height'])
        section.top_margin = Cm(self.config['margin_top'])
        section.bottom_margin = Cm(self.config['margin_bottom'])
        section.left_margin = Cm(self.config['margin_left'])
        section.right_margin = Cm(self.config['margin_right'])

        # 页脚距离边界 (页码位置)
        section.footer_distance = Cm(1.0)

    def detect_heading_level(self, text):
        """检测段落属于哪个层级标题"""
        if not text:
            return 0

        if LEVEL1_PATTERN.match(text):
            return 1
        if LEVEL2_PATTERN.match(text):
            return 2
        if LEVEL3_PATTERN.match(text):
            return 3
        if LEVEL4_PATTERN.match(text):
            return 4
        return 0

    def set_run_font(self, run, font_name, size_pt, bold=False):
        """设置run的中英文字体、字号"""
        run.font.name = font_name
        run.font.size = Pt(size_pt)
        run.font.bold = bold
        # 设置东亚字体（中文字体）
        rPr = run._element.get_or_add_rPr()
        rFonts = rPr.find(qn('w:rFonts'))
        if rFonts is None:
            rFonts = OxmlElement('w:rFonts')
            rPr.insert(0, rFonts)
        rFonts.set(qn('w:eastAsia'), font_name)
        rFonts.set(qn('w:ascii'), font_name)
        rFonts.set(qn('w:hAnsi'), font_name)

    def set_paragraph_line_spacing_fixed(self, para, pt_value):
        """设置段落行距为固定值"""
        pPr = para._element.get_or_add_pPr()
        spacing = pPr.find(qn('w:spacing'))
        if spacing is None:
            spacing = OxmlElement('w:spacing')
            pPr.append(spacing)
        spacing.set(qn('w:line'), str(int(pt_value * 20)))  # 1pt = 20 twips
        spacing.set(qn('w:lineRule'), 'exact')

    def format_paragraphs(self):
        """格式化所有段落"""
        paragraphs = self.doc.paragraphs
        total = len(paragraphs)

        for idx, para in enumerate(paragraphs):
            text = para.text.strip()

            if not text:
                # 空段落保留但清除多余格式
                continue

            level = self.detect_heading_level(text)

            # ---- 判断是否为公文标题（第一个非空段落，且内容较短） ----
            is_doc_title = False
            if idx == 0 or (idx < 3 and not is_doc_title):
                # 第一个非空段落作为公文标题
                prev_empty = True
                for j in range(idx - 1, -1, -1):
                    if self.doc.paragraphs[j].text.strip():
                        prev_empty = False
                        break
                if prev_empty and len(text) < 50:
                    is_doc_title = True

            # ---- 根据层级设置字体 ----
            if is_doc_title:
                font_name = self.config['title_font']
                font_size = self.config['title_size']
                bold = self.config['title_bold']
                alignment = WD_ALIGN_PARAGRAPH.CENTER
                first_indent = 0
            elif level == 1:
                font_name = self.config['h1_font']
                font_size = self.config['h1_size']
                bold = self.config['h1_bold']
                alignment = WD_ALIGN_PARAGRAPH.LEFT
                first_indent = 0  # 一级标题顶格
            elif level == 2:
                font_name = self.config['h2_font']
                font_size = self.config['h2_size']
                bold = self.config['h2_bold']
                alignment = WD_ALIGN_PARAGRAPH.LEFT
                first_indent = 0
            elif level == 3:
                font_name = self.config['h3_font']
                font_size = self.config['h3_size']
                bold = self.config['h3_bold']
                alignment = WD_ALIGN_PARAGRAPH.LEFT
                first_indent = 0
            elif level == 4:
                font_name = self.config['h4_font']
                font_size = self.config['h4_size']
                bold = self.config['h4_bold']
                alignment = WD_ALIGN_PARAGRAPH.LEFT
                first_indent = 0
            else:
                font_name = self.config['body_font']
                font_size = self.config['body_size']
                bold = False
                alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                first_indent = self.config['first_line_indent']

            # ---- 应用字体到所有run ----
            for run in para.runs:
                self.set_run_font(run, font_name, font_size, bold)

            # 如果段落没有run（空run），加一个
            if not para.runs:
                run = para.add_run(text)
                self.set_run_font(run, font_name, font_size, bold)

            # ---- 段落对齐 ----
            para.alignment = alignment

            # ---- 首行缩进 ----
            if first_indent > 0:
                # 首行缩进2字符 (2字符 × 字号pt)
                para.paragraph_format.first_line_indent = Pt(font_size * first_indent)
            else:
                para.paragraph_format.first_line_indent = Pt(0)

            # ---- 行距：固定值 ----
            self.set_paragraph_line_spacing_fixed(para, self.config['line_spacing_fixed'])

            # ---- 段前段后间距 ----
            if level >= 1 and level <= 4:
                # 标题段前段后各空一行 (约等于一个正文行)
                para.paragraph_format.space_before = Pt(self.config['line_spacing_fixed'])
                para.paragraph_format.space_after = Pt(self.config['line_spacing_fixed'])
            else:
                para.paragraph_format.space_before = Pt(0)
                para.paragraph_format.space_after = Pt(0)

    def add_page_number(self):
        """添加公文样式页码: 4号半角阿拉伯数字, 底端外侧, 一字线"""
        section = self.doc.sections[0]

        # 为奇偶页创建不同的页脚
        section.different_first_page_header_footer = False

        footer = section.footer
        footer.is_linked_to_previous = False

        # 清空默认页脚
        for p in footer.paragraphs:
            p.clear()

        fp = footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.LEFT  # 通过制表位控制左右

        # 方案：插入 "— PAGE —" 格式
        run1 = fp.add_run('—')
        self.set_run_font(run1, 'Times New Roman', 14, False)

        # 插入页码域
        run2 = fp.add_run()
        self.set_run_font(run2, 'Times New Roman', 14, False)

        fldChar_begin = OxmlElement('w:fldChar')
        fldChar_begin.set(qn('w:fldCharType'), 'begin')
        run2._element.append(fldChar_begin)

        instrText = OxmlElement('w:instrText')
        instrText.set(qn('xml:space'), 'preserve')
        instrText.text = ' PAGE '
        run2._element.append(instrText)

        fldChar_end = OxmlElement('w:fldChar')
        fldChar_end.set(qn('w:fldCharType'), 'end')
        run2._element.append(fldChar_end)

        run3 = fp.add_run('—')
        self.set_run_font(run3, 'Times New Roman', 14, False)

        # 设置段落缩进: 单页码居右空一字，双页码居左空一字
        # 通过偶数字号空格来模拟
        # 注意：这里简化处理，Word中精确的"外侧"需要奇偶页不同页脚
        # 使用制表位实现粗略效果
        tab_stops = fp.paragraph_format.tab_stops
        tab_stops.add_tab_stop(Cm(14.0), alignment=WD_ALIGN_PARAGRAPH.RIGHT)
        fp.paragraph_format.first_line_indent = Pt(0)

    def format_attachment_label(self):
        """处理附件标记"""
        # 附件应在正文下空1行，左空2字标注
        # 在正文中查找"附件"或"附件："开头的段落
        for para in self.doc.paragraphs:
            text = para.text.strip()
            if text.startswith('附件') or text.startswith('附件：') or text.startswith('附件:'):
                # 设置为仿宋，左空2字
                for run in para.runs:
                    self.set_run_font(run, self.config['body_font'], self.config['body_size'], False)
                if not para.runs:
                    run = para.add_run(text)
                    self.set_run_font(run, self.config['body_font'], self.config['body_size'], False)
                para.alignment = WD_ALIGN_PARAGRAPH.LEFT
                para.paragraph_format.first_line_indent = Pt(self.config['body_size'] * 2)
                break

    def run(self):
        """执行全部排版"""
        self.set_page_layout()
        self.format_paragraphs()
        self.add_page_number()
        self.format_attachment_label()
        return self.doc


# ============================================================
# Flask 路由
# ============================================================

@format_bp.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('请选择文件', 'error')
            return render_template('format.html')

        file = request.files['file']
        if file.filename == '':
            flash('请选择文件', 'error')
            return render_template('format.html')

        if not file.filename.lower().endswith('.docx'):
            flash('仅支持 .docx 格式', 'error')
            return render_template('format.html')

        try:
            doc = Document(file)

            # 构建配置（允许用户覆盖）
            config = DEFAULT_CONFIG.copy()
            try:
                # 页边距覆盖
                config['margin_top'] = float(request.form.get('margin_top', config['margin_top']))
                config['margin_bottom'] = float(request.form.get('margin_bottom', config['margin_bottom']))
                config['margin_left'] = float(request.form.get('margin_left', config['margin_left']))
                config['margin_right'] = float(request.form.get('margin_right', config['margin_right']))
                # 行距
                config['line_spacing_fixed'] = float(request.form.get('line_spacing', config['line_spacing_fixed']))
                # 正文字号
                config['body_size'] = float(request.form.get('body_size', config['body_size']))
                # 标题字号
                config['title_size'] = float(request.form.get('title_size', config['title_size']))
            except ValueError:
                pass

            # 执行排版
            formatter = DocumentFormatter(doc, config)
            formatter.run()

            # 保存
            output = io.BytesIO()
            doc.save(output)
            output.seek(0)

            original_name = file.filename
            if original_name.lower().endswith('.docx'):
                original_name = original_name[:-5]
            output_name = f"{original_name}_已排版.docx"

            return send_file(
                output,
                as_attachment=True,
                download_name=output_name,
                mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )

        except Exception as e:
            flash(f'处理出错: {str(e)}', 'error')
            return render_template('format.html')

    return render_template('format.html')
