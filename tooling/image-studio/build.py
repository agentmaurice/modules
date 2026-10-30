#!/usr/bin/env python3
"""Generate the image-studio Module resources (manifest, Workflows, MiniApp).

Every code step runs the one Go/WASM action of image-studio/wasm/studio,
pinned by artifact.json (sha256 and size of the signed build). Rebuild the
action with `maurice module wasm build`, record its artifact here, then run
this script; the offline tests check that the resources match this output.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULE = ROOT.parents[1] / 'image-studio'
DEST = MODULE / 'agents/main'
VERSION = '0.1.0'
ARTIFACT = json.loads((ROOT / 'artifact.json').read_text(encoding='utf-8'))
IMAGE_TOOL = 'multimodal--multimodal_image_generate_v1'
VISION_TOOL = 'multimodal--multimodal_vision_analyze_v1'
REF_TOOL = 'multimodal--multimodal_ref_read_v1'
DEFAULT_PROFILE = '/image-studio/profiles/ribin-avatar-item.json'
PLANNER_SCHEMA = json.loads((ROOT / 'planner-schema.json').read_text(encoding='utf-8'))


def OPT(key):
    """An optional input: an absent key renders as an empty string."""
    return '{{ ' + key + ' | default "" }}'


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def studio(action_id, op, context, output_key):
    """A step of the Go/WASM action; the op selects the function."""
    return {'id': action_id, 'type': 'code_execution', 'runtime': 'wasm',
            'artifact': {'sha256': ARTIFACT['sha256'], 'size': ARTIFACT['size']},
            'context': {'op': op, **context}, 'output_key': output_key}


def tool(action_id, name, params, output_key):
    return {'id': action_id, 'type': 'tool_call', 'tool': name, 'params': params, 'output_key': output_key}


def call(action_id, workflow_id, inputs, output_key):
    return {'id': action_id, 'type': 'workflow_call', 'workflow_id': workflow_id, 'workflow_version': '1',
            'execution': 'sync', 'input': inputs, 'output_key': output_key}


def schema(required, **props):
    return {'type': 'object', 'required': required, 'properties': props}


def text(description, **extra):
    return {'type': 'string', 'description': description, **extra}


def obj(description):
    return {'type': 'object', 'description': description}


def workflow(workflow_id, title, description, input_schema, actions, output, forms=None):
    data = {'$schema': 'agentmaurice.workflow/v2', 'schema_version': 2, 'workflow_id': workflow_id, 'kind': 'workflow',
            'title': title, 'version': '1', 'description': description, 'input_schema': input_schema}
    if forms:
        data['forms'] = forms
    data.update({'actions': actions, 'output': output})
    dump(DEST / 'workflows' / f'{workflow_id}.json', data)
    return data


def generate(prompt):
    return tool('generate', IMAGE_TOOL, {'prompt': prompt, 'aspect_ratio': '{{ job.aspect_ratio }}',
                                         'model': '{{ job.model }}'}, 'generated')


def review(attempt_key):
    """Vision review of the attempt, then the text of its answer."""
    return [tool('review', VISION_TOOL, {
        'inputs': [{'type': 'image', 'mime_type': 'image/png', 'content': {'data': '{{ ' + attempt_key + '.judge_image }}'}}],
        'tasks': ['describe'], 'prompt': '{{ job.judge_prompt }}',
    }, 'review'),
        # The vision answer comes back as a buffer reference: read its text.
        tool('read-review', REF_TOOL, {'ref': '{{ (index .review.outputs 0).ref }}'}, 'review_text')]


COMMON = {
    'pack_id': text('Pack identifier: lowercase letters, digits and hyphens', pattern='^[a-z0-9][a-z0-9-]{0,47}$'),
    'theme': text('Theme written into the documents; defaults to the pack id'),
    'profile_path': text('Storage path of the output profile'),
    'root': text('Storage folder of the packs; defaults to /image-studio/packs'),
}
JOB = {'job': obj('One asset job produced by the style sheet')}
ATTEMPT_INPUT = schema(['job', 'attempt', 'verdict'], job=obj('Asset job'), attempt=obj('Result of the attempt op'),
                       verdict=obj('Result of the verdict op'))


def build():
    pack_fields = [
        {'name': 'brief', 'type': 'text', 'required': True, 'title': 'Brief',
         'description': 'What the pack is about, in a few sentences'},
        {'name': 'pack_id', 'type': 'string', 'required': True, 'title': 'Pack id', 'description': 'noel-2026'},
        {'name': 'profile_path', 'type': 'string', 'required': True, 'title': 'Profile', 'default': DEFAULT_PROFILE},
        {'name': 'max_assets', 'type': 'number', 'required': True, 'title': 'Number of assets', 'default': 12},
    ]
    workflow('image-studio-plan', 'Plan an image pack',
             'Turns a brief into an art direction and a typed asset list that satisfies the output profile, and stores plan.json.',
             schema(['brief', 'pack_id', 'profile_path'], brief=text('Brief of the pack'),
                    max_assets={'type': ['integer', 'string'], 'description': 'Number of assets to plan, capped by the profile'}, **COMMON),
             [studio('prepare', 'prepare_plan', {'profile_path': '{{ profile_path }}', 'brief': '{{ brief }}',
                                                 'max_assets': OPT('max_assets')}, 'prep'),
              {'id': 'draft', 'type': 'llm_call', 'llm_prompt': '{{ prep.planner_prompt }}',
               'llm_system_prompt': 'You are the art director of a small game studio. You answer with JSON only.',
               'llm_temperature': 0.4, 'llm_max_tokens': 8000, 'llm_response_format': 'json',
               'llm_response_schema': PLANNER_SCHEMA, 'output_key': 'draft'},
              studio('normalize', 'plan', {'profile': '{{ prep.profile }}', 'draft': '{{ draft }}', 'brief': '{{ brief }}',
                                           'pack_id': '{{ pack_id }}', 'theme': OPT('theme'), 'root': OPT('root'),
                                           'max_assets': '{{ prep.max_assets }}'}, 'planned')],
             {'plan': '{{ planned.plan }}', 'profile': '{{ prep.profile }}', 'plan_file': '{{ planned.file }}'})

    workflow('image-studio-style-sheet', 'Build the style sheet of a pack',
             'Derives the prompt material shared by every image of a plan, stores style.json and returns one job per asset.',
             schema(['profile', 'plan'], profile=obj('Output profile'), plan=obj('Normalized plan'), root=COMMON['root']),
             [studio('style', 'style_sheet', {'profile': '{{ profile }}', 'plan': '{{ plan }}', 'root': OPT('root')}, 'sheet')],
             {'style': '{{ sheet.style }}', 'jobs': '{{ sheet.jobs }}', 'style_file': '{{ sheet.file }}'})

    workflow('image-studio-produce-asset', 'Produce one asset',
             'Generates the image, stores it, exports it with the profile, has it reviewed by the vision tool, then '
             'keeps it or makes one corrected second attempt. Never fails on a weak image: it reports its status.',
             schema(['job'], **JOB),
             [generate('{{ job.prompt }}'),
              studio('attempt', 'attempt', {'job': '{{ job }}', 'generated': '{{ generated }}', 'attempt': 1}, 'first'),
              *review('first'),
              studio('judge', 'verdict', {'job': '{{ job }}', 'attempt': '{{ first }}', 'review': '{{ review_text }}',
                                          'final': False}, 'verdict'),
              {'id': 'decide', 'type': 'decision', 'input': '{{ verdict.next }}', 'selector': {'mode': 'input'},
               'choices': [
                   {'id': 'accept', 'description': 'The first attempt passed', 'workflow_id': 'image-studio-asset-finalize'},
                   {'id': 'retry', 'description': 'One corrected second attempt', 'workflow_id': 'image-studio-asset-retry'}],
               'fallback': {'id': 'hold', 'description': 'Unexpected verdict: write nothing and report the asset as held',
                            'workflow_id': 'image-studio-asset-hold'},
               'child_input': {'job': '{{ job }}', 'attempt': '{{ first }}', 'verdict': '{{ verdict }}'},
               'output_key': 'decision', 'result_key': 'outcome'}],
             {'asset': '{{ outcome.asset }}', 'decision': '{{ decision.choice }}'})

    workflow('image-studio-asset-finalize', 'Keep an attempt',
             'Writes the kept attempt as the asset: exported file, profile document and file hashes.',
             ATTEMPT_INPUT,
             [studio('finalize', 'finalize', {'job': '{{ job }}', 'attempt': '{{ attempt }}', 'verdict': '{{ verdict }}'}, 'asset')],
             {'asset': '{{ asset }}'})

    workflow('image-studio-asset-hold', 'Hold an asset',
             'Fallback of the production decision: writes nothing and reports the asset as held for a human. The '
             'verdict op only answers accept or retry, so this branch is a guard.',
             ATTEMPT_INPUT, [],
             {'asset': {'record': 'image-studio.held/v1', 'id': '{{ job.asset.id }}', 'index': '{{ job.index }}',
                        'dir': '{{ job.dir }}', 'status': 'held'}})

    workflow('image-studio-asset-retry', 'Second attempt',
             'Generates again with the reasons of the first refusal, reviews the result and keeps it; a weak second '
             'attempt is kept with the needs_review status.',
             ATTEMPT_INPUT,
             [generate('{{ verdict.retry_prompt }}'),
              studio('attempt', 'attempt', {'job': '{{ job }}', 'generated': '{{ generated }}', 'attempt': 2}, 'second'),
              *review('second'),
              studio('judge', 'verdict', {'job': '{{ job }}', 'attempt': '{{ second }}', 'review': '{{ review_text }}',
                                          'final': True}, 'final_verdict'),
              studio('finalize', 'finalize', {'job': '{{ job }}', 'attempt': '{{ second }}',
                                              'verdict': '{{ final_verdict }}'}, 'asset')],
             {'asset': '{{ asset }}'})

    workflow('image-studio-publish', 'Publish a pack to Storage',
             'Writes the SHA-256 manifest, the review sheet and review.json of a pack. Nothing leaves Storage.',
             schema(['pack_id', 'assets'], pack_id=COMMON['pack_id'], root=COMMON['root'],
                    title=text('Pack title'), profile=text('Profile key'),
                    assets={'description': 'Asset records, or Workflow outputs that contain them'}),
             [studio('publish', 'publish', {'pack_id': '{{ pack_id }}', 'root': OPT('root'), 'title': OPT('title'),
                                            'profile': '{{ profile }}', 'assets': '{{ assets }}'}, 'published')],
             {'pack_id': '{{ published.pack_id }}', 'manifest_path': '{{ published.manifest_path }}',
              'manifest_sha256': '{{ published.manifest_sha256 }}', 'review_sheet_path': '{{ published.review_sheet_path }}',
              'assets': '{{ published.assets }}', 'counts': '{{ published.counts }}'})

    workflow('image-studio-pack', 'Produce an image pack',
             'From a brief to a reviewed pack in Storage: plan, style sheet, one production per asset (two bounded '
             'attempts), then manifest and review sheet. Publication outside Storage stays a human step.',
             schema(['brief', 'pack_id', 'profile_path'], brief=text('Brief of the pack'),
                    max_assets={'type': ['integer', 'string'], 'description': 'Number of assets to plan, capped by the profile'}, **COMMON),
             [call('plan', 'image-studio-plan', {'brief': '{{ brief }}', 'pack_id': '{{ pack_id }}', 'theme': OPT('theme'),
                                                 'profile_path': '{{ profile_path }}', 'root': OPT('root'),
                                                 'max_assets': OPT('max_assets')}, 'planned'),
              call('style', 'image-studio-style-sheet', {'profile': '{{ planned.data.profile }}',
                                                         'plan': '{{ planned.data.plan }}', 'root': OPT('root')}, 'styled'),
              {'id': 'produce', 'type': 'for_each', 'items': '{{ styled.data.jobs }}', 'item_key': 'job',
               'max_items': 20, 'on_empty': 'fail', 'workflow_id': 'image-studio-produce-asset', 'output_key': 'produced'},
              call('publish', 'image-studio-publish', {'pack_id': '{{ pack_id }}', 'root': OPT('root'),
                                                       'title': '{{ planned.data.plan.title }}',
                                                       'profile': '{{ planned.data.profile.key }}',
                                                       'assets': '{{ produced }}'}, 'published')],
             {'pack_id': '{{ pack_id }}', 'title': '{{ planned.data.plan.title }}',
              'manifest_path': '{{ published.data.manifest_path }}', 'manifest_sha256': '{{ published.data.manifest_sha256 }}',
              'review_sheet_path': '{{ published.data.review_sheet_path }}', 'counts': '{{ published.data.counts }}',
              'plan_issues': '{{ planned.data.plan.issues }}'},
             forms=[{'id': 'pack', 'title': 'Produce a pack', 'fields': pack_fields,
                     'actions_on_submit': ['plan', 'style', 'produce', 'publish']}])

    workflow('image-studio-render', 'Render one image',
             'One image from a brief with any profile (for example a raster shop banner): job, production with two '
             'bounded attempts, manifest and review sheet.',
             schema(['brief', 'pack_id', 'asset_id', 'profile_path'], brief=text('What the image shows'),
                    asset_id=text('Asset identifier'), title=text('Display title'),
                    category=text('Profile category; defaults to the first one'),
                    placement=text('Category placement, when the profile defines placements'), **COMMON),
             [studio('prepare', 'single_job', {'brief': '{{ brief }}', 'asset_id': '{{ asset_id }}', 'title': OPT('title'),
                                               'category': OPT('category'), 'placement': OPT('placement'), 'pack_id': '{{ pack_id }}', 'theme': OPT('theme'),
                                               'profile_path': '{{ profile_path }}', 'root': OPT('root')}, 'prepared'),
              call('produce', 'image-studio-produce-asset', {'job': '{{ prepared.job }}'}, 'produced'),
              call('publish', 'image-studio-publish', {'pack_id': '{{ pack_id }}', 'root': OPT('root'), 'title': OPT('title'),
                                                       'profile': '{{ prepared.job.profile }}', 'assets': '{{ produced }}'},
                   'published')],
             {'pack_id': '{{ pack_id }}', 'manifest_path': '{{ published.data.manifest_path }}',
              'manifest_sha256': '{{ published.data.manifest_sha256 }}',
              'review_sheet_path': '{{ published.data.review_sheet_path }}', 'counts': '{{ published.data.counts }}'})

    workflow('image-studio-export', 'Export a stored image',
             'Exports an image already in Storage with a profile, without generating anything.',
             schema(['source_path', 'out_dir', 'profile_path'], source_path=text('Storage path of the source image'),
                    out_dir=text('Storage folder of the export'), profile_path=COMMON['profile_path'],
                    category=text('Profile category; defaults to the first one'), placement=text('Category placement')),
             [studio('export', 'export', {'source_path': '{{ source_path }}', 'out_dir': '{{ out_dir }}',
                                          'profile_path': '{{ profile_path }}', 'category': OPT('category'),
                                          'placement': OPT('placement')}, 'exported')],
             {'file': '{{ exported.file }}', 'stats': '{{ exported.stats }}', 'source': '{{ exported.source }}'})

    workflow('image-studio-profile-save', 'Save an output profile',
             'Validates an image-studio.profile/v1 document and stores it in Storage.',
             schema(['profile', 'path'], profile=obj('Profile document'), path=text('Storage path, for example ' + DEFAULT_PROFILE)),
             [studio('save', 'save_profile', {'profile': '{{ profile }}', 'path': '{{ path }}'}, 'saved')],
             {'key': '{{ saved.key }}', 'kind': '{{ saved.kind }}', 'file': '{{ saved.file }}'})

    workflow('image-studio-review-read', 'Read the review of a pack',
             'Returns review.json of a pack for the review MiniApp.',
             schema(['pack_id'], pack_id=COMMON['pack_id'], root=COMMON['root']),
             [studio('read', 'read_review', {'pack_id': '{{ pack_id }}', 'root': OPT('root')}, 'review')],
             {'pack_id': '{{ review.pack_id }}', 'title': '{{ review.title }}', 'assets': '{{ review.assets }}',
              'counts': '{{ review.counts }}', 'manifest': '{{ review.manifest }}',
              'manifest_sha256': '{{ review.manifest_sha256 }}', 'review_sheet': '{{ review.review_sheet }}'},
             forms=[{'id': 'review', 'title': 'Review a pack', 'fields': [
                 {'name': 'pack_id', 'type': 'string', 'required': True, 'title': 'Pack id', 'description': 'noel-2026'}],
                 'actions_on_submit': ['read']}])

    miniapp()
    manifest()


def miniapp():
    data = {
        '$schema': 'agentmaurice.miniapp/v2', 'schema_version': 2, 'miniapp_id': 'image-studio-review', 'kind': 'miniapp',
        'title': 'Image studio', 'version': '1',
        'description': 'Review a produced pack before any human publication.',
        'ui': {'renderer': 'component', 'component': 'image-studio-review', 'configuration': {'layout': [
            {'type': 'callout', 'title': 'Human review', 'tone': 'info',
             'value': 'Packs stay in Storage. Run image-studio-pack, then open its review here: check the review sheet and every '
                      'asset before publishing with your own tools.'},
            {'type': 'section', 'title': 'Pack review', 'children': [
                {'type': 'kpi_grid', 'items': [
                    {'label': 'Accepted', 'value': {'state': 'review.counts.accepted'}, 'tone': 'success'},
                    {'label': 'Needs review', 'value': {'state': 'review.counts.needs_review'}, 'tone': 'warning'}]},
                {'type': 'stat', 'label': 'Review sheet', 'value': {'state': 'review.review_sheet'}},
                {'type': 'stat', 'label': 'Manifest', 'value': {'state': 'review.manifest'}},
                {'type': 'table', 'columns': ['index', 'id', 'title', 'category', 'status', 'score', 'attempts'],
                 'column_labels': {'index': '#', 'id': 'Id', 'title': 'Title', 'category': 'Category', 'status': 'Status',
                                   'score': 'Score', 'attempts': 'Attempts'},
                 'rows': {'state': 'review.assets'}}]},
]}},
        'state_schema': {'type': 'object', 'properties': {
            'pack_id': {'type': 'string'}, 'review': {'type': 'object'}}},
        'initial_state': {'pack_id': '', 'review': {'counts': {'accepted': 0, 'needs_review': 0}, 'assets': [], 'review_sheet': '',
                                     'manifest': ''}},
        'events': [
            {'event_id': 'review-pack', 'trigger': 'form.submit',
             'workflow': {'workflow_id': 'image-studio-review-read', 'input': {'pack_id': '{{ state.pack_id }}'}},
             'result_to_state': 'review'}],
    }
    dump(DEST / 'miniapps' / 'image-studio-review.json', data)


def manifest():
    def ref(key, name):
        return {'key': key, 'name': name, 'workflow_id': key, 'workflow_version': '1'}
    data = {
        '$schema': 'agentmaurice.module/v2', 'schema_version': 2, 'key': 'image-studio', 'name': 'Image studio',
        'version': VERSION,
        'provides': {
            'actions': [ref('image-studio-pack', 'Produce an image pack'), ref('image-studio-render', 'Render one image'),
                        ref('image-studio-plan', 'Plan an image pack'), ref('image-studio-style-sheet', 'Build a style sheet'),
                        ref('image-studio-produce-asset', 'Produce one asset'),
                        ref('image-studio-asset-finalize', 'Keep an attempt'), ref('image-studio-asset-retry', 'Second attempt'),
                        ref('image-studio-asset-hold', 'Hold an asset'),
                        ref('image-studio-publish', 'Publish a pack to Storage'), ref('image-studio-export', 'Export a stored image'),
                        ref('image-studio-profile-save', 'Save an output profile')],
            'queries': [ref('image-studio-review-read', 'Read the review of a pack')],
            'apps': [{'key': 'image-studio-review', 'name': 'Image studio', 'miniapp_id': 'image-studio-review',
                      'miniapp_version': '1'}]},
        'requires': {},
    }
    dump(MODULE / 'module.yaml', data)


if __name__ == '__main__':
    build()
