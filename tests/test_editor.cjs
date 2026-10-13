// Behavioral checks execute the production editor script in a small DOM fixture.
// Run with Node 18+: node tests/test_editor.cjs
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');

class Element {
  constructor(tag = 'div') {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.dataset = {};
    this.style = {};
    this.handlers = {};
    this.attributes = {};
    this.value = '';
    this.className = '';
    this.classList = {
      add: (...names) => { this.className += ` ${names.join(' ')}`; },
      toggle: () => {},
      contains: name => this.className.split(' ').includes(name),
    };
    this.lastChild = { textContent: '' };
  }
  append(...items) { items.forEach(item => { item.parent = this; this.children.push(item); }); }
  insertBefore(item, before) { item.parent = this; this.children.splice(this.children.indexOf(before), 0, item); }
  replaceChildren(...items) { this.children = []; this.append(...items); }
  setAttribute(name, value) { this.attributes[name] = value; }
  setAttributeNS(_, name, value) { this.setAttribute(name, value); }
  addEventListener(name, handler) { (this.handlers[name] ??= []).push(handler); }
  emit(name, event) { for (const handler of this.handlers[name] || []) handler(event); }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter(item => item !== this); }
  focus() { this.focused = true; }
  click() {}
  close() { this.open = false; }
  showModal() { this.open = true; }
  scrollIntoView() {}
  setPointerCapture() {}
  hasPointerCapture() { return false; }
  getBoundingClientRect() { return { left: 0, top: 0, width: 1200, height: 900 }; }
  closest(selector) {
    if (selector.includes('contenteditable') && ['true', 'plaintext-only'].includes(this.contentEditable)) return this;
    if (selector === '.text-annotation' && this.className.includes('text-annotation')) return this;
    if (selector === '[data-ann]' && this.dataset.ann) return this;
    return this.parent?.closest(selector) || null;
  }
  matches(selector) {
    if (selector === 'tspan') return this.tagName === 'TSPAN';
    const annotation = selector.match(/data-ann="([^"]+)"/);
    if (annotation && this.dataset.ann !== annotation[1]) return false;
    const tag = selector.match(/^[a-z]+/);
    if (tag && this.tagName !== tag[0].toUpperCase()) return false;
    const classes = [...selector.matchAll(/\.([\w-]+)/g)].map(match => match[1]);
    return classes.every(name => this.className.split(' ').includes(name)) && (!!annotation || classes.length > 0 || !!tag);
  }
  querySelectorAll(selector) {
    return this.children.flatMap(child => [...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  getContext() { return { fillRect() {}, measureText: text => ({ width: text.length * 12 }) }; }
  toDataURL() { return 'data:image/png;base64,aW1hZ2U='; }
}

function fixture() {
  const elements = new Map();
  const get = selector => {
    if (!elements.has(selector)) elements.set(selector, new Element());
    return elements.get(selector);
  };
  const document = new Element('document');
  document.querySelector = get;
  document.querySelectorAll = () => [];
  document.createElement = tag => new Element(tag);
  document.createElementNS = (_, tag) => new Element(tag);
  document.createRange = () => ({ selectNodeContents() {} });
  document.body = new Element('body');
  const window = new Element('window');
  window.structuredClone = structuredClone;
  window.confirm = () => true;
  window.setTimeout = () => 1;
  window.setInterval = () => 1;
  window.getSelection = () => ({ removeAllRanges() {}, addRange() {} });
  const downloads = [];
  const context = {
    document, window, navigator: {}, structuredClone, Blob, console, performance,
    clearInterval() {}, requestAnimationFrame: callback => callback(),
    CSS: { escape: text => text },
    URL: { createObjectURL(blob) { downloads.push(blob); return 'blob:test'; }, revokeObjectURL() {} },
    Image: class { set src(_) { queueMicrotask(() => this.onload()); } },
    FileReader: class {
      async readAsDataURL(blob) {
        this.result = `data:${blob.type || 'image/png'};base64,${Buffer.from(await blob.arrayBuffer()).toString('base64')}`;
        this.onload();
      }
    },
    FormData: class { append() {} },
    fetch: async () => ({ ok: true, json: async () => ({}), blob: async () => new Blob(['image'], { type: 'image/png' }) }),
  };
  const source = fs.readFileSync(path.join(__dirname, '..', 'static', 'app.js'), 'utf8');
  const exposed = `globalThis.editorTest = {state, elements, checkpoint, undo, redo, setSelection,
    pointerDown, pointerMove, pointerUp, startResize, resizeSelection, beginTextEdit,
    updateSelectedProperty, openFile, openProject, exportProject, exportDocument, duplicateSelection,
    renderAll};`;
  vm.runInNewContext(source.replace(/\}\)\(\);\s*$/, `${exposed}\n})();`), context);
  const editor = context.editorTest;
  editor.state.zoom = 1;
  const text = { id: 'text', type: 'text', x: 40, y: 40, width: 200, height: 40,
    text: 'Original', fontSize: 24, opacity: 1, color: '#000000', bold: false };
  editor.state.pages[0].annotations = [text];
  editor.setSelection(['text']);
  editor.renderAll();
  return { editor, context, get, downloads, text };
}

function pointer(target, x = 50, y = 50) {
  return { target, button: 0, pointerId: 1, clientX: x, clientY: y, preventDefault() {} };
}

async function run() {
  let passed = 0;
  const test = async (name, callback) => { await callback(); console.log(`PASS ${name}`); passed++; };
  await test('Click without moving preserves redo history', () => {
    const { editor, get } = fixture();
    editor.state.future = [{ pages: [] }];
    editor.pointerDown(pointer(get('#stage').querySelector('.text-annotation')));
    editor.pointerUp({ pointerId: 1 });
    assert.equal(editor.state.future.length, 1);
    assert.equal(editor.state.history.length, 0);
  });
  await test('Drag changes position and undo/redo restores it', () => {
    const { editor, get, text } = fixture();
    editor.pointerDown(pointer(get('#stage').querySelector('.text-annotation')));
    editor.pointerMove(pointer(get('#stage'), 80, 90));
    editor.pointerUp({ pointerId: 1 });
    assert.equal(text.x, 70);
    assert.equal(text.y, 80);
    editor.undo();
    assert.equal(editor.state.pages[0].annotations[0].x, 40);
    editor.redo();
    assert.equal(editor.state.pages[0].annotations[0].x, 70);
  });
  await test('Resize click without moving preserves redo history', () => {
    const { editor } = fixture();
    editor.state.future = [{ pages: [] }];
    editor.startResize([240, 40], 1);
    editor.pointerUp({ pointerId: 1 });
    assert.equal(editor.state.future.length, 1);
    assert.equal(editor.state.history.length, 0);
  });
  await test('Selection badge is removed before text editing', () => {
    const { editor, get } = fixture();
    const text = get('#stage').querySelector('.text-annotation');
    assert.ok(text.querySelector('.selection-badge'));
    editor.beginTextEdit(text);
    assert.equal(text.querySelector('.selection-badge'), null);
    assert.equal(text.contentEditable, 'plaintext-only');
  });
  await test('Native undo is left available inside editable text', () => {
    const { editor, get, context } = fixture();
    const text = get('#stage').querySelector('.text-annotation');
    editor.beginTextEdit(text);
    let prevented = false;
    context.document.emit('keydown', {target: text, ctrlKey: true, key: 'z', preventDefault() { prevented = true; }});
    assert.equal(prevented, false);
  });
  await test('PNG export keeps unsaved project status', async () => {
    const { editor, get } = fixture();
    editor.state.dirty = true;
    get('#exportDialog').querySelector = () => ({value: 'png'});
    await editor.exportDocument();
    assert.equal(editor.state.dirty, true);
  });
  await test('Project export saves vector layer, scale, table metadata, and clears dirty', async () => {
    const { editor, get, downloads } = fixture();
    editor.state.pages[0].pdfData = 'JVBERg==';
    editor.state.pages[0].pointsPerPixel = 0.625;
    editor.state.pages[0].annotations[0].table = {id: 'table', row: 0, column: 0};
    editor.state.dirty = true;
    get('#exportDialog').querySelector = () => ({value: 'pdfeditorathome'});
    await editor.exportDocument();
    const saved = JSON.parse(await downloads[0].text());
    assert.equal(saved.version, 2);
    assert.equal(saved.pages[0].pdfData, 'JVBERg==');
    assert.equal(saved.pages[0].pointsPerPixel, 0.625);
    assert.equal(saved.pages[0].annotations[0].table.id, 'table');
    assert.equal(editor.state.dirty, false);
  });
  await test('Malformed project leaves the current document untouched', async () => {
    const { editor } = fixture();
    const before = editor.state.pages;
    await editor.openProject({text: async () => JSON.stringify({format: 'pdfeditorathome', version: 2,
      name: 'Broken', pages: [{width: 0, height: 100, annotations: []}]})});
    assert.equal(editor.state.pages, before);
    assert.equal(editor.state.name, 'Untitled document');
    assert.equal(editor.state.opening, false);
  });
  await test('Project round trip restores embedded layers and scale', async () => {
    const { editor } = fixture();
    await editor.openProject({text: async () => JSON.stringify({format: 'pdfeditorathome', version: 2,
      name: 'Restored', pages: [{width: 100, height: 200, imageData: 'data:image/png;base64,aW1hZ2U=',
        pdfData: 'JVBERg==', pointsPerPixel: 0.625, annotations: []}]})});
    assert.equal(editor.state.name, 'Restored');
    assert.equal(editor.state.pages[0].pdfData, 'JVBERg==');
    assert.equal(editor.state.pages[0].pointsPerPixel, 0.625);
  });
  await test('Imported pages are embedded before replacing the document', async () => {
    const { editor, context } = fixture();
    context.fetch = async url => ({ ok: true,
      json: async () => ({name: 'Import', documentId: 'cache', sourceFormat: 'pdf', editableTextCount: 0,
        pages: [{width: 100, height: 200, imageUrl: '/preview', pdfUrl: '/vector', pointsPerPixel: 0.625, annotations: []}]}),
      blob: async () => new Blob(['background'], {type: url === '/vector' ? 'application/pdf' : 'image/png'}),
    });
    await editor.openFile({name: 'sample.pdf'});
    assert.ok(editor.state.pages[0].imageData.startsWith('data:image/png;base64,'));
    assert.ok(editor.state.pages[0].pdfData);
    assert.equal(editor.state.pages[0].pointsPerPixel, 0.625);
  });
  await test('Font size changes update PDF text baseline and dimensions', () => {
    const { editor, text } = fixture();
    text.noWrap = true;
    text.baselineY = 64;
    editor.updateSelectedProperty('fontSize', 48);
    assert.equal(text.baselineY, 88);
    assert.equal(text.width, 400);
    assert.equal(text.height, 80);
  });
  await test('Duplicated table text is detached from the original cell', () => {
    const { editor, text } = fixture();
    text.table = {id: 'original-table', row: 0, column: 0};
    editor.duplicateSelection();
    assert.ok(text.table);
    assert.equal(editor.state.pages[0].annotations[1].table, undefined);
  });
  console.log(`${passed} editor behavior checks passed.`);
}

module.exports = run();
module.exports.catch(error => { console.error(error); process.exitCode = 1; });
