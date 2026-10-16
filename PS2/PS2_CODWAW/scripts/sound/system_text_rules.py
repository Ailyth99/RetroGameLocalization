"""System text that the user wants to keep in its original English."""

# Menu_Am HTXT contains the Rebellion and Activision credit pages. The save
# dialogs at 411/412 are interleaved and must not be treated as staff credits.
# Shared navigation (e.g. Continue at 32) is outside the credit-page content.
STAFFROLL_MENU_INDICES = frozenset(range(354, 368)) | frozenset(range(403, 411)) | frozenset(range(413, 479))


def is_staffroll_reference(ref):
    return (ref['file'] == 'Misc/Menu/Menu_Am.asr'
            and ref['key'].startswith('HTXT:')
            and int(ref['key'].split(':')[1]) in STAFFROLL_MENU_INDICES)


def preserved_english_reason(entry):
    if entry['id'] == 'T0349':
        return '开场版权及商标声明按约定保留英文。'
    if any(is_staffroll_reference(ref) for ref in entry['references']):
        return 'STAFFROLL 全部内容按约定保留英文，包括职位、部门、姓名、鸣谢及声明。'
    return ''
