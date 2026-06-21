"""
Word排版工具 - 一键格式美化
功能：上传Word文档，自动设置格式后下载
"""
import os
import io
import re
import datetime
from docx import Document
from docx.shared import Pt, Cm, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from flask import Blueprint, render_template, request, send_file, flash

format_bp = Blueprint('format', __name__, url_prefix='/format')

# 默认排版配置
DEFAULT_CONFIG = {
    'title_font': '黑体',
    'title_size': 16,       # 二号 ≈ 22pt，小二号 ≈ 18pt
    'body_font': '仿宋',
    'body_size': 16,        # 三号 ≈ 16pt
    'line_spacing': 1.5,    # 1.5 倍行距
    'first_line_indent': 2, # 首行缩进2字符（em单位）
    'page_margin_top': 2.54,      # cm
    'page_margin_bottom': 2.54,   # cm
    'page_margin_left': 3.18,     # cm
    'page_margin_right': 3.18,    # cm
    'page_number': True,
    'generate_toc': True,
}


def set_cell_border(table_cell, **kwargs):
    """设置表格边框"""
    tc = table_cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement('w:tcBorders')
    for edge in ('start', 'top', 'end', 'bottom', 'insideH', 'insideV'):
        edge_data = kwargs.get(edge)
        if edge_data:
            element = OxmlElement(f'w:{edge}')
            for key in ['sz', 'val', 'color', 'space']:
                if key in edge_data:
                    element.set(qn(f'w:{key}'), str(edge_data[key]))
            tcBorders.append(element)
    tcPr.append(tcBorders)


def auto_format_document(doc, config=None):
    """对Document对象执行自动排版"""
    if config is None:
        config = DEFAULT_CONFIG

    # ---- 页面设置 ----
    section = doc.sections[0]
    section.top_margin = Cm(config['page_margin_top'])
    section.bottom_margin = Cm(config['page_margin_bottom'])
    section.left_margin = Cm(config['page_margin_left'])
    section.right_margin = Cm(config['page_margin_right'])

    paragraphs = doc.paragraphs
    total = len(paragraphs)

    for idx, para in enumerate(paragraphs):
        text = para.text.strip()

        # 跳过空段落
        if not text:
            continue

        # 检测是否为标题（基于字号或是否为前几行短文本）
        is_title = False
        if idx == 0:
            is_title = True  # 第一个非空段落视为标题

        for run in para.runs:
            run.font.name = config['title_font'] if is_title else config['body_font']
            run._element.rPr.rFonts.set(qn('w:eastAsia'),
                                        config['title_font'] if is_title else config['body_font'])

            if is_title:
                run.font.size = Pt(config['title_size'])
                run.font.bold = True
            else:
                run.font.size = Pt(config['body_size'])
                run.font.bold = False

        # 段落对齐
        if is_title:
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        else:
            para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            # 首行缩进2字符
            para.paragraph_format.first_line_indent = Pt(config['body_size'] * config['first_line_indent'])

        # 行距
        para.paragraph_format.line_spacing = config['line_spacing']

    # ---- 页脚页码 ----
    if config.get('page_number', False):
        section = doc.sections[0]
        footer = section.footer
        footer.is_linked_to_previous = False
        fp = footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = fp.add_run()
        fldChar1 = OxmlElement('w:fldChar')
        fldChar1.set(qn('w:fldCharType'), 'begin')
        run._element.append(fldChar1)

        instrText = OxmlElement('w:instrText')
        instrText.set(qn('xml:space'), 'preserve')
        instrText.text = ' PAGE '
        run._element.append(instrText)

        fldChar2 = OxmlElement('w:fldChar')
        fldChar2.set(qn('w:fldCharType'), 'end')
        run._element.append(fldChar2)

    # ---- 自动目录（书签式目录） ----
    # 注意：Word的真实TOC需要宏，这里用段落目录作为替代
    if config.get('generate_toc', False) and total > 5:
        # 在第一页插入一个简单的标记目录
        first_para = doc.paragraphs[0] if doc.paragraphs else None
        if first_para:
            # 插入目录标题
            toc_para = doc.paragraphs[0].insert_paragraph_before()
            toc_para.text = ""
            # 硬插入一个TOC域
            run = toc_para.add_run("【目录】")
            run.font.name = '黑体'
            run.font.size = Pt(16)
            run.font.bold = True
            run._element.rPr.rFonts.set(qn('w:eastAsia'), '黑体')
            toc_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

            # 添加各段落的简单跳转
            for i, p in enumerate(doc.paragraphs):
                t = p.text.strip()
                if len(t) > 3 and i > 0 and i < 20 and len(t) < 60:
                    # 作为子目录项
                    sub_para = doc.paragraphs[i].insert_paragraph_before()
                    sub_run = sub_para.add_run(f"  · {t}")
                    sub_run.font.name = '仿宋'
                    sub_run.font.size = Pt(14)
                    sub_run._element.rPr.rFonts.set(qn('w:eastAsia'), '仿宋')

    return doc


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
            # 读取上传的文档
            doc = Document(file)

            # 收集用户自定义配置
            config = DEFAULT_CONFIG.copy()
            try:
                config['title_size'] = float(request.form.get('title_size', config['title_size']))
                config['body_size'] = float(request.form.get('body_size', config['body_size']))
                config['line_spacing'] = float(request.form.get('line_spacing', config['line_spacing']))
                config['page_margin_top'] = float(request.form.get('margin_top', config['page_margin_top']))
                config['page_margin_bottom'] = float(request.form.get('margin_bottom', config['page_margin_bottom']))
                config['page_margin_left'] = float(request.form.get('margin_left', config['page_margin_left']))
                config['page_margin_right'] = float(request.form.get('margin_right', config['page_margin_right']))
            except ValueError:
                pass

            # 执行排版
            auto_format_document(doc, config)

            # 保存到内存
            output = io.BytesIO()
            doc.save(output)
            output.seek(0)

            # 生成文件名
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
