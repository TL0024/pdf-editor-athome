(() => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const clone = (value) => window.structuredClone ? structuredClone(value) : JSON.parse(JSON.stringify(value));
  const uid = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`;
  const projectFormat = 'pdfeditorathome';

  const elements = {
    stage: $('#stage'),
    scroller: $('#canvasScroller'),
    workspace: $('#workspace'),
    pageList: $('#pageList'),
    pageCount: $('#pageCount'),
    pageStatus: $('#pageStatus'),
    fileInput: $('#fileInput'),
    title: $('#documentTitle'),
    saveState: $('#saveState'),
    openButton: $('#openButton'),
    exportButton: $('#exportButton'),
    addPageButton: $('#addPageButton'),
    duplicatePageButton: $('#duplicatePageButton'),
    deletePageButton: $('#deletePageButton'),
    undoButton: $('#undoButton'),
    redoButton: $('#redoButton'),
    zoomOutButton: $('#zoomOutButton'),
    zoomInButton: $('#zoomInButton'),
    zoomLabel: $('#zoomLabel'),
    toolGroup: $('#toolGroup'),
    emptyProperties: $('#emptyProperties'),
    propertiesContent: $('#propertiesContent'),
    propertiesTitle: $('#propertiesTitle'),
    textProperties: $('#textProperties'),
    strokeProperties: $('#strokeProperties'),
    colorInput: $('#colorInput'),
    fontSizeInput: $('#fontSizeInput'),
    boldButton: $('#boldButton'),
    coverButton: $('#coverButton'),
    lineWidthInput: $('#lineWidthInput'),
    lineWidthOutput: $('#lineWidthOutput'),
    opacityInput: $('#opacityInput'),
    opacityOutput: $('#opacityOutput'),
    duplicateSelectionButton: $('#duplicateSelectionButton'),
    deleteSelectionButton: $('#deleteSelectionButton'),
    exportDialog: $('#exportDialog'),
    confirmExportButton: $('#confirmExportButton'),
    formatGrid: $('#formatGrid'),
    busyOverlay: $('#busyOverlay'),
    busyTitle: $('#busyTitle'),
    busySubtitle: $('#busySubtitle'),
    dropHint: $('#dropHint'),
    toastRegion: $('#toastRegion'),
  };

  const state = {
    name: 'Untitled document',
    documentId: null,
    sourceFormat: null,
    pages: [],
    selectedPage: 0,
    selectedId: null,
    selectedIds: [],
    tool: 'select',
    zoom: 0.6,
    history: [],
    future: [],
    dirty: false,
    drawing: null,
    dragging: null,
    marquee: null,
    resizing: null,
    clipboard: null,
    propertyCheckpointed: false,
    lastTextClick: null,
    defaults: {
      text: { color: '#1f2937', fontSize: 24, fontFamily: 'Arial, sans-serif', opacity: 1, bold: false, italic: false, cover: false },
      pen: { color: '#4f46e5', lineWidth: 4, opacity: 1 },
      highlight: { color: '#f6c744', lineWidth: 24, opacity: 0.35 },
    },
  };

  function createBlankImage(width = 1240, height = 1754) {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d');
    context.fillStyle = '#ffffff';
    context.fillRect(0, 0, width, height);
    return canvas.toDataURL('image/png');
  }

  function makeBlankPage() {
    return {
      id: uid(),
      width: 1240,
      height: 1754,
      imageData: createBlankImage(),
      imageUrl: null,
      documentId: null,
      serverIndex: null,
      annotations: [],
    };
  }

  function currentPage() {
    return state.pages[state.selectedPage];
  }

  function currentAnnotations() {
    return currentPage()?.annotations || [];
  }

  function selectedAnnotation() {
    return currentAnnotations().find(annotation => annotation.id === state.selectedId) || null;
  }

  function selectedAnnotations() {
    const selected = new Set(state.selectedIds);
    return currentAnnotations().filter(annotation => selected.has(annotation.id));
  }

  function isSelected(id) {
    return state.selectedIds.includes(id);
  }

  function setSelection(ids, primaryId = null) {
    const available = new Set(currentAnnotations().map(annotation => annotation.id));
    state.selectedIds = [...new Set(ids)].filter(id => available.has(id));
    state.selectedId = primaryId && state.selectedIds.includes(primaryId)
      ? primaryId
      : state.selectedIds[state.selectedIds.length - 1] || null;
  }

  function clearSelection() {
    state.selectedIds = [];
    state.selectedId = null;
  }

  function snapshot() {
    return {
      pages: state.pages.map(page => ({ ...page, annotations: clone(page.annotations) })),
      selectedPage: state.selectedPage,
      selectedId: state.selectedId,
      selectedIds: [...state.selectedIds],
      name: state.name,
    };
  }

  function checkpoint() {
    state.history.push(snapshot());
    if (state.history.length > 50) state.history.shift();
    state.future = [];
    updateHistoryButtons();
  }

  function restoreSnapshot(value) {
    state.pages = value.pages;
    state.selectedPage = Math.min(value.selectedPage, state.pages.length - 1);
    state.selectedIds = value.selectedIds || (value.selectedId ? [value.selectedId] : []);
    state.selectedId = value.selectedId || state.selectedIds[state.selectedIds.length - 1] || null;
    state.name = value.name;
    elements.title.value = state.name;
    setDirty(true);
    renderAll();
  }

  function undo() {
    if (!state.history.length) return;
    state.future.push(snapshot());
    restoreSnapshot(state.history.pop());
    updateHistoryButtons();
  }

  function redo() {
    if (!state.future.length) return;
    state.history.push(snapshot());
    restoreSnapshot(state.future.pop());
    updateHistoryButtons();
  }

  function updateHistoryButtons() {
    elements.undoButton.disabled = state.history.length === 0;
    elements.redoButton.disabled = state.future.length === 0;
  }

  function setDirty(dirty) {
    state.dirty = dirty;
    elements.saveState.classList.toggle('dirty', dirty);
    elements.saveState.lastChild.textContent = dirty ? ' Unsaved changes' : ' Ready';
  }

  function showBusy(title, subtitle) {
    elements.busyTitle.textContent = title;
    elements.busySubtitle.textContent = subtitle;
    elements.busyOverlay.hidden = false;
  }

  function hideBusy() {
    elements.busyOverlay.hidden = true;
  }

  function toast(message, type = 'success') {
    const item = document.createElement('div');
    item.className = `toast ${type}`;
    item.textContent = message;
    elements.toastRegion.append(item);
    window.setTimeout(() => item.remove(), 3600);
  }

  function imageSource(page) {
    return page.imageData || page.imageUrl || '';
  }

  function renderAll() {
    renderPageList();
    renderStage();
    renderProperties();
    updateStatus();
    updateHistoryButtons();
  }

  function renderPageList() {
    elements.pageList.replaceChildren();
    state.pages.forEach((page, index) => {
      const item = document.createElement('div');
      item.className = `page-thumbnail${index === state.selectedPage ? ' active' : ''}`;
      item.dataset.page = String(index);
      item.tabIndex = 0;
      item.setAttribute('role', 'button');
      item.setAttribute('aria-label', `Open page ${index + 1}`);

      const wrap = document.createElement('div');
      wrap.className = 'thumbnail-image-wrap';
      const pageSurface = document.createElement('div');
      pageSurface.className = `thumbnail-page ${page.width / page.height > 1.25 ? 'fit-width' : 'fit-height'}`;
      pageSurface.style.aspectRatio = `${page.width} / ${page.height}`;
      const image = document.createElement('img');
      image.src = imageSource(page);
      image.alt = `Page ${index + 1} preview`;
      const overlay = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      overlay.classList.add('thumbnail-overlay');
      overlay.setAttribute('viewBox', `0 0 ${page.width} ${page.height}`);
      overlay.setAttribute('aria-hidden', 'true');
      page.annotations.filter(annotation => annotation.type === 'stroke').forEach(annotation => {
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.setAttribute('d', strokePath(annotation.points));
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke', annotation.color);
        path.setAttribute('stroke-width', String(annotation.lineWidth));
        path.setAttribute('stroke-linecap', 'round');
        path.setAttribute('stroke-linejoin', 'round');
        path.setAttribute('opacity', String(annotation.opacity));
        overlay.append(path);
      });
      page.annotations.filter(annotation => annotation.type === 'text' && annotation.noWrap).forEach(annotation => {
        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        text.classList.add('thumbnail-text-svg');
        text.setAttributeNS('http://www.w3.org/XML/1998/namespace', 'xml:space', 'preserve');
        text.setAttribute('x', String(annotation.x));
        text.setAttribute('y', String(annotation.baselineY ?? annotation.y + annotation.fontSize * 0.9));
        text.setAttribute('fill', annotation.color);
        text.setAttribute('opacity', String(annotation.opacity));
        text.setAttribute('font-size', String(annotation.fontSize));
        text.setAttribute('font-family', annotation.fontFamily || 'Arial, sans-serif');
        text.setAttribute('font-weight', annotation.bold ? '700' : '400');
        text.setAttribute('font-style', annotation.italic ? 'italic' : 'normal');
        const lines = String(annotation.text).split('\n');
        lines.forEach((line, lineIndex) => {
          const tspan = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
          tspan.setAttributeNS('http://www.w3.org/XML/1998/namespace', 'xml:space', 'preserve');
          tspan.setAttribute('x', String(annotation.x));
          if (lineIndex) tspan.setAttribute('dy', String(annotation.fontSize * 1.15));
          if (lines.length === 1 && line && annotation.width > 0) {
            tspan.setAttribute('textLength', String(annotation.width));
            tspan.setAttribute('lengthAdjust', 'spacing');
          }
          tspan.textContent = line || ' ';
          text.append(tspan);
        });
        overlay.append(text);
      });
      page.annotations.filter(annotation => annotation.type === 'text' && !annotation.noWrap).forEach(annotation => {
        const foreignObject = document.createElementNS('http://www.w3.org/2000/svg', 'foreignObject');
        foreignObject.setAttribute('x', String(annotation.x));
        foreignObject.setAttribute('y', String(annotation.y));
        foreignObject.setAttribute('width', String(annotation.width));
        foreignObject.setAttribute('height', String(Math.max(annotation.height, annotation.fontSize * 1.3)));
        const text = document.createElement('div');
        text.className = 'thumbnail-flow-text';
        text.style.fontSize = `${annotation.fontSize}px`;
        text.style.fontFamily = annotation.fontFamily || 'Arial, sans-serif';
        text.style.fontStyle = annotation.italic ? 'italic' : 'normal';
        text.style.fontWeight = annotation.bold ? '700' : '400';
        text.style.color = annotation.color;
        text.style.opacity = annotation.opacity;
        text.style.background = annotation.cover ? 'white' : 'transparent';
        text.textContent = annotation.text;
        foreignObject.append(text);
        overlay.append(foreignObject);
      });
      pageSurface.append(image, overlay);
      wrap.append(pageSurface);

      const meta = document.createElement('div');
      meta.className = 'thumbnail-meta';
      const label = document.createElement('strong');
      label.textContent = `Page ${index + 1}`;
      const annotationCount = document.createElement('span');
      annotationCount.innerHTML = page.annotations.length ? `<i class="annotation-dot"></i> ${page.annotations.length}` : 'Blank edits';
      meta.append(label, annotationCount);
      item.append(wrap, meta);
      item.addEventListener('click', () => selectPage(index));
      item.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') selectPage(index);
      });
      elements.pageList.append(item);
    });
    elements.pageCount.textContent = `${state.pages.length} ${state.pages.length === 1 ? 'page' : 'pages'}`;
  }

  function strokePath(points) {
    if (!points?.length) return '';
    if (points.length === 1) return `M ${points[0][0]} ${points[0][1]} l .1 .1`;
    let path = `M ${points[0][0]} ${points[0][1]}`;
    for (let index = 1; index < points.length - 1; index++) {
      const point = points[index];
      const next = points[index + 1];
      path += ` Q ${point[0]} ${point[1]} ${(point[0] + next[0]) / 2} ${(point[1] + next[1]) / 2}`;
    }
    const last = points[points.length - 1];
    path += ` L ${last[0]} ${last[1]}`;
    return path;
  }

  function renderStage() {
    const page = currentPage();
    if (!page) return;
    const zoom = state.zoom;
    elements.stage.className = `page-stage stage-${state.tool}`;
    elements.stage.style.width = `${page.width * zoom}px`;
    elements.stage.style.height = `${page.height * zoom}px`;
    elements.stage.replaceChildren();

    const background = document.createElement('img');
    background.className = 'page-background';
    background.src = imageSource(page);
    background.alt = '';
    background.draggable = false;
    elements.stage.append(background);

    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'drawing-layer');
    svg.setAttribute('viewBox', `0 0 ${page.width} ${page.height}`);
    svg.setAttribute('width', String(page.width * zoom));
    svg.setAttribute('height', String(page.height * zoom));
    page.annotations.filter(item => item.type === 'stroke').forEach(annotation => {
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.dataset.ann = annotation.id;
      path.classList.add('drawing-stroke');
      if (isSelected(annotation.id)) path.classList.add('selected');
      path.setAttribute('d', strokePath(annotation.points));
      path.setAttribute('stroke', annotation.color);
      path.setAttribute('stroke-width', String(annotation.lineWidth));
      path.setAttribute('opacity', String(annotation.opacity));
      svg.append(path);
    });
    const firstDrawingStroke = svg.querySelector('.drawing-stroke');
    const insertBelowDrawings = node => firstDrawingStroke ? svg.insertBefore(node, firstDrawingStroke) : svg.append(node);
    page.annotations.filter(item => item.type === 'text' && item.noWrap).forEach(annotation => {
      if (isSelected(annotation.id)) {
        const selection = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        selection.dataset.ann = annotation.id;
        selection.classList.add('pdf-text-selection');
        selection.setAttribute('x', String(annotation.x));
        selection.setAttribute('y', String(annotation.y));
        selection.setAttribute('width', String(Math.max(annotation.width, 2)));
        selection.setAttribute('height', String(Math.max(annotation.height, annotation.fontSize)));
        insertBelowDrawings(selection);
      }
      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.dataset.ann = annotation.id;
      text.classList.add('pdf-text-svg');
      text.setAttributeNS('http://www.w3.org/XML/1998/namespace', 'xml:space', 'preserve');
      text.setAttribute('x', String(annotation.x));
      text.setAttribute('y', String(annotation.baselineY ?? annotation.y + annotation.fontSize * 0.9));
      text.setAttribute('fill', annotation.color);
      text.setAttribute('opacity', String(annotation.opacity));
      text.setAttribute('font-size', String(annotation.fontSize));
      text.setAttribute('font-family', annotation.fontFamily || 'Arial, sans-serif');
      text.setAttribute('font-weight', annotation.bold ? '700' : '400');
      text.setAttribute('font-style', annotation.italic ? 'italic' : 'normal');
      const lines = String(annotation.text).split('\n');
      lines.forEach((line, index) => {
        const tspan = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
        tspan.setAttributeNS('http://www.w3.org/XML/1998/namespace', 'xml:space', 'preserve');
        tspan.setAttribute('x', String(annotation.x));
        if (index) tspan.setAttribute('dy', String(annotation.fontSize * 1.15));
        if (lines.length === 1 && line && annotation.width > 0) {
          tspan.setAttribute('textLength', String(annotation.width));
          tspan.setAttribute('lengthAdjust', 'spacing');
        }
        tspan.textContent = line || ' ';
        text.append(tspan);
      });
      insertBelowDrawings(text);
    });
    elements.stage.append(svg);

    page.annotations.filter(item => item.type === 'text' && !item.noWrap).forEach(annotation => {
      const text = document.createElement('div');
      text.className = `text-annotation${isSelected(annotation.id) ? ' selected' : ''}`;
      text.classList.toggle('cover-underneath', Boolean(annotation.cover));
      text.classList.toggle('imported-text', annotation.source === 'imported');
      text.dataset.ann = annotation.id;
      text.style.left = `${annotation.x * zoom}px`;
      text.style.top = `${annotation.y * zoom}px`;
      text.style.width = `${annotation.width * zoom}px`;
      text.style.minHeight = `${annotation.height * zoom}px`;
      text.style.fontSize = `${annotation.fontSize * zoom}px`;
      text.style.fontFamily = annotation.fontFamily || 'Arial, sans-serif';
      text.style.fontStyle = annotation.italic ? 'italic' : 'normal';
      text.style.color = annotation.color;
      text.style.opacity = annotation.opacity;
      text.style.fontWeight = annotation.bold ? '700' : '400';
      text.textContent = annotation.text;
      if (annotation.id === state.selectedId && state.tool === 'select') {
        const badge = document.createElement('span');
        badge.className = 'selection-badge';
        badge.textContent = state.selectedIds.length > 1 ? `${state.selectedIds.length} selected` : 'Text';
        text.append(badge);
      }
      elements.stage.append(text);
    });
    renderGroupSelectionBox();
  }

  function updateStrokeElement(annotation) {
    const element = elements.stage.querySelector(`path[data-ann="${CSS.escape(annotation.id)}"]`);
    if (element) element.setAttribute('d', strokePath(annotation.points));
  }

  function updatePdfTextElement(annotation) {
    const text = elements.stage.querySelector(`text.pdf-text-svg[data-ann="${CSS.escape(annotation.id)}"]`);
    if (text) {
      text.setAttribute('x', String(annotation.x));
      text.setAttribute('y', String(annotation.baselineY ?? annotation.y + annotation.fontSize * 0.9));
      $$('tspan', text).forEach(tspan => tspan.setAttribute('x', String(annotation.x)));
    }
    const selection = elements.stage.querySelector(`rect.pdf-text-selection[data-ann="${CSS.escape(annotation.id)}"]`);
    if (selection) {
      selection.setAttribute('x', String(annotation.x));
      selection.setAttribute('y', String(annotation.y));
    }
  }

  function renderProperties() {
    const annotation = selectedAnnotation();
    const annotations = selectedAnnotations();
    const hasSelection = annotations.length > 0;
    elements.propertiesTitle.textContent = annotations.length > 1 ? `${annotations.length} selected` : 'Properties';
    elements.emptyProperties.hidden = hasSelection;
    elements.propertiesContent.hidden = !hasSelection;
    $('.properties-panel').classList.toggle('has-selection', hasSelection);
    if (!annotation) return;

    elements.colorInput.value = annotation.color;
    elements.opacityInput.value = Math.round(annotation.opacity * 100);
    elements.opacityOutput.textContent = `${Math.round(annotation.opacity * 100)}%`;
    const allText = annotations.every(item => item.type === 'text');
    const allStrokes = annotations.every(item => item.type === 'stroke');
    elements.textProperties.hidden = !allText;
    elements.strokeProperties.hidden = !allStrokes;
    if (allText) {
      elements.fontSizeInput.value = annotation.fontSize;
      elements.boldButton.classList.toggle('active', Boolean(annotation.bold));
      elements.coverButton.classList.toggle('active', Boolean(annotation.cover));
    } else if (allStrokes) {
      elements.lineWidthInput.value = annotation.lineWidth;
      elements.lineWidthOutput.textContent = annotation.lineWidth;
    }
  }

  function updateStatus() {
    elements.pageStatus.textContent = `Page ${state.selectedPage + 1} of ${state.pages.length}`;
    elements.zoomLabel.textContent = `${Math.round(state.zoom * 100)}%`;
    elements.deletePageButton.disabled = state.pages.length <= 1;
  }

  function selectPage(index) {
    if (index < 0 || index >= state.pages.length) return;
    state.selectedPage = index;
    clearSelection();
    renderAll();
    const activeThumb = $(`.page-thumbnail[data-page="${index}"]`, elements.pageList);
    activeThumb?.scrollIntoView({ block: 'nearest' });
  }

  function selectAnnotation(id) {
    setSelection([id], id);
    renderStage();
    renderProperties();
  }

  function setTool(tool) {
    state.tool = tool;
    $$('.tool-button', elements.toolGroup).forEach(button => button.classList.toggle('active', button.dataset.tool === tool));
    if (tool !== 'select') clearSelection();
    renderStage();
    renderProperties();
  }

  function stagePoint(event) {
    const rect = elements.stage.getBoundingClientRect();
    const page = currentPage();
    return [
      Math.max(0, Math.min((event.clientX - rect.left) / state.zoom, page.width)),
      Math.max(0, Math.min((event.clientY - rect.top) / state.zoom, page.height)),
    ];
  }

  function annotationFromTarget(target) {
    const element = target.closest?.('[data-ann]');
    return element ? currentAnnotations().find(item => item.id === element.dataset.ann) : null;
  }

  function hitAnnotation(point) {
    const [x, y] = point;
    const annotations = [...currentAnnotations()].reverse();
    for (const annotation of annotations) {
      if (annotation.type === 'text' && x >= annotation.x && x <= annotation.x + annotation.width && y >= annotation.y && y <= annotation.y + annotation.height) return annotation;
      if (annotation.type === 'stroke') {
        const threshold = Math.max(annotation.lineWidth / 2 + 8, 12);
        if (annotation.points.some(candidate => Math.hypot(candidate[0] - x, candidate[1] - y) <= threshold)) return annotation;
      }
    }
    return null;
  }

  function annotationBounds(annotation) {
    if (annotation.type === 'text') {
      return {
        left: annotation.x,
        top: annotation.y,
        right: annotation.x + annotation.width,
        bottom: annotation.y + annotation.height,
      };
    }
    const points = annotation.points || [];
    if (!points.length) return null;
    const padding = Math.max(Number(annotation.lineWidth || 1) / 2, 2);
    const xs = points.map(point => Number(point[0]));
    const ys = points.map(point => Number(point[1]));
    return {
      left: Math.min(...xs) - padding,
      top: Math.min(...ys) - padding,
      right: Math.max(...xs) + padding,
      bottom: Math.max(...ys) + padding,
    };
  }

  function combinedBounds(annotations = selectedAnnotations()) {
    const bounds = annotations.map(annotationBounds).filter(Boolean);
    if (!bounds.length) return null;
    return bounds.reduce((combined, item) => ({
      left: Math.min(combined.left, item.left),
      top: Math.min(combined.top, item.top),
      right: Math.max(combined.right, item.right),
      bottom: Math.max(combined.bottom, item.bottom),
    }));
  }

  function renderGroupSelectionBox() {
    if (state.tool !== 'select' || !state.selectedIds.length) return;
    const bounds = combinedBounds();
    if (!bounds) return;
    const box = document.createElement('div');
    box.className = `group-selection-box${state.selectedIds.length > 1 ? ' multi' : ''}`;
    box.style.left = `${bounds.left * state.zoom}px`;
    box.style.top = `${bounds.top * state.zoom}px`;
    box.style.width = `${Math.max(bounds.right - bounds.left, 2) * state.zoom}px`;
    box.style.height = `${Math.max(bounds.bottom - bounds.top, 2) * state.zoom}px`;
    const handle = document.createElement('button');
    handle.type = 'button';
    handle.className = 'selection-resize-handle';
    handle.setAttribute('aria-label', 'Resize selection from top right');
    handle.title = 'Drag to resize. Hold Ctrl to preserve proportions.';
    box.append(handle);
    elements.stage.append(box);
  }

  function normalizedRect(start, end) {
    return {
      left: Math.min(start[0], end[0]),
      top: Math.min(start[1], end[1]),
      right: Math.max(start[0], end[0]),
      bottom: Math.max(start[1], end[1]),
    };
  }

  function boundsIntersect(first, second) {
    return first && second
      && first.left <= second.right
      && first.right >= second.left
      && first.top <= second.bottom
      && first.bottom >= second.top;
  }

  function renderMarquee() {
    if (!state.marquee) return;
    let marquee = $('.marquee-selection', elements.stage);
    if (!marquee) {
      marquee = document.createElement('div');
      marquee.className = 'marquee-selection';
      elements.stage.append(marquee);
    }
    const rect = normalizedRect(state.marquee.start, state.marquee.current);
    marquee.style.left = `${rect.left * state.zoom}px`;
    marquee.style.top = `${rect.top * state.zoom}px`;
    marquee.style.width = `${(rect.right - rect.left) * state.zoom}px`;
    marquee.style.height = `${(rect.bottom - rect.top) * state.zoom}px`;
  }

  function startMarquee(point, additive, pointerId) {
    const baseIds = additive ? [...state.selectedIds] : [];
    if (!additive) clearSelection();
    state.marquee = { start: point, current: point, baseIds };
    elements.stage.setPointerCapture(pointerId);
    renderStage();
    renderProperties();
    renderMarquee();
  }

  function finishMarquee() {
    if (!state.marquee) return;
    const rect = normalizedRect(state.marquee.start, state.marquee.current);
    const moved = rect.right - rect.left > 2 || rect.bottom - rect.top > 2;
    const hits = moved
      ? currentAnnotations().filter(annotation => boundsIntersect(rect, annotationBounds(annotation))).map(annotation => annotation.id)
      : [];
    setSelection([...state.marquee.baseIds, ...hits], hits[hits.length - 1] || state.selectedId);
    state.marquee = null;
    renderAll();
  }

  function startResize(point, pointerId) {
    const annotations = selectedAnnotations();
    const bounds = combinedBounds(annotations);
    if (!annotations.length || !bounds) return;
    checkpoint();
    const originals = {};
    annotations.forEach(annotation => {
      originals[annotation.id] = annotation.type === 'text'
        ? {
            x: annotation.x, y: annotation.y, width: annotation.width, height: annotation.height,
            baselineY: annotation.baselineY, fontSize: annotation.fontSize,
          }
        : { points: clone(annotation.points), lineWidth: annotation.lineWidth };
    });
    state.resizing = {
      ids: annotations.map(annotation => annotation.id),
      bounds,
      anchor: [bounds.left, bounds.bottom],
      originals,
      start: point,
      moved: false,
    };
    elements.stage.setPointerCapture(pointerId);
  }

  function resizeSelection(point, preserveRatio) {
    const resize = state.resizing;
    if (!resize) return;
    const originalWidth = Math.max(resize.bounds.right - resize.bounds.left, 1);
    const originalHeight = Math.max(resize.bounds.bottom - resize.bounds.top, 1);
    let scaleX = Math.max((point[0] - resize.anchor[0]) / originalWidth, 0.1);
    let scaleY = Math.max((resize.anchor[1] - point[1]) / originalHeight, 0.1);
    if (preserveRatio) {
      const scale = Math.abs(scaleX - 1) >= Math.abs(scaleY - 1) ? scaleX : scaleY;
      scaleX = scale;
      scaleY = scale;
    }
    resize.moved = resize.moved || Math.abs(scaleX - 1) + Math.abs(scaleY - 1) > 0.01;
    currentAnnotations().filter(annotation => resize.ids.includes(annotation.id)).forEach(annotation => {
      const original = resize.originals[annotation.id];
      if (annotation.type === 'text') {
        annotation.x = resize.anchor[0] + (original.x - resize.anchor[0]) * scaleX;
        annotation.y = resize.anchor[1] + (original.y - resize.anchor[1]) * scaleY;
        annotation.width = Math.max(original.width * scaleX, 8);
        annotation.height = Math.max(original.height * scaleY, 8);
        annotation.fontSize = Math.max(original.fontSize * scaleY, 4);
        if (Number.isFinite(original.baselineY)) {
          annotation.baselineY = resize.anchor[1] + (original.baselineY - resize.anchor[1]) * scaleY;
        }
      } else {
        annotation.points = original.points.map(([x, y]) => [
          resize.anchor[0] + (x - resize.anchor[0]) * scaleX,
          resize.anchor[1] + (y - resize.anchor[1]) * scaleY,
        ]);
        annotation.lineWidth = Math.max(original.lineWidth * Math.sqrt(scaleX * scaleY), 1);
      }
    });
    renderStage();
    renderProperties();
  }

  function addText(point) {
    checkpoint();
    const defaults = state.defaults.text;
    const page = currentPage();
    const annotation = {
      id: uid(), type: 'text', x: point[0], y: point[1],
      width: Math.min(300, page.width - point[0] - 12), height: 44,
      text: 'Type here', ...defaults,
    };
    page.annotations.push(annotation);
    setSelection([annotation.id], annotation.id);
    setDirty(true);
    setTool('select');
    requestAnimationFrame(() => {
      const text = elements.stage.querySelector(`[data-ann="${CSS.escape(annotation.id)}"]`);
      beginTextEdit(text, true);
    });
    renderPageList();
  }

  function beginTextEdit(element, selectAll = false) {
    if (!element) return;
    element.contentEditable = 'true';
    element.dataset.editStarted = 'false';
    element.focus();
    if (selectAll) {
      const range = document.createRange();
      range.selectNodeContents(element);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
    }
  }

  function beginPdfTextEdit(annotation, selectAll = false) {
    const svgText = elements.stage.querySelector(`text.pdf-text-svg[data-ann="${CSS.escape(annotation.id)}"]`);
    if (svgText) svgText.style.visibility = 'hidden';
    const editor = document.createElement('div');
    editor.className = 'text-annotation imported-text pdf-text-editor selected';
    editor.dataset.ann = annotation.id;
    editor.style.left = `${annotation.x * state.zoom}px`;
    editor.style.top = `${(annotation.baselineY - annotation.fontSize * 0.9) * state.zoom}px`;
    editor.style.width = `${Math.max(annotation.width, 20) * state.zoom}px`;
    editor.style.minHeight = `${Math.max(annotation.height, annotation.fontSize) * state.zoom}px`;
    editor.style.fontSize = `${annotation.fontSize * state.zoom}px`;
    editor.style.fontFamily = annotation.fontFamily || 'Arial, sans-serif';
    editor.style.fontStyle = annotation.italic ? 'italic' : 'normal';
    editor.style.fontWeight = annotation.bold ? '700' : '400';
    editor.style.color = annotation.color;
    editor.style.opacity = annotation.opacity;
    editor.textContent = annotation.text;
    elements.stage.append(editor);
    beginTextEdit(editor, selectAll);
  }

  function beginAnnotationEdit(annotation, selectAll = false) {
    if (!annotation) return;
    if (annotation.noWrap) {
      beginPdfTextEdit(annotation, selectAll);
      return;
    }
    const text = elements.stage.querySelector(`.text-annotation[data-ann="${CSS.escape(annotation.id)}"]`);
    beginTextEdit(text, selectAll);
  }

  const textMeasureCanvas = document.createElement('canvas');
  const textMeasureContext = textMeasureCanvas.getContext('2d');

  function measureTextAnnotation(annotation, text) {
    textMeasureContext.font = `${annotation.italic ? 'italic ' : ''}${annotation.bold ? '700' : '400'} ${annotation.fontSize}px ${annotation.fontFamily || 'Arial, sans-serif'}`;
    return Math.max(...String(text).split('\n').map(line => textMeasureContext.measureText(line || ' ').width), annotation.fontSize);
  }

  function startStroke(point) {
    checkpoint();
    const style = state.tool === 'highlight' ? state.defaults.highlight : state.defaults.pen;
    const annotation = { id: uid(), type: 'stroke', tool: state.tool, points: [point], ...style };
    currentPage().annotations.push(annotation);
    state.drawing = annotation;
    setSelection([annotation.id], annotation.id);
    setDirty(true);
    renderStage();
  }

  function deleteAnnotation(id, addCheckpoint = true) {
    const index = currentAnnotations().findIndex(item => item.id === id);
    if (index < 0) return;
    if (addCheckpoint) checkpoint();
    currentAnnotations().splice(index, 1);
    setSelection(state.selectedIds.filter(selectedId => selectedId !== id));
    setDirty(true);
    renderAll();
  }

  function duplicateSelection() {
    const annotations = selectedAnnotations();
    if (!annotations.length) return;
    checkpoint();
    const copies = annotations.map(annotation => {
      const copy = clone(annotation);
      copy.id = uid();
      if (copy.type === 'text') {
        copy.x += 16;
        copy.y += 16;
        if (Number.isFinite(copy.baselineY)) copy.baselineY += 16;
      } else {
        copy.points = copy.points.map(([x, y]) => [x + 16, y + 16]);
      }
      return copy;
    });
    currentAnnotations().push(...copies);
    setSelection(copies.map(copy => copy.id), copies[copies.length - 1].id);
    setDirty(true);
    renderAll();
  }

  function deleteSelection() {
    const selected = new Set(state.selectedIds);
    if (!selected.size) return;
    checkpoint();
    currentPage().annotations = currentAnnotations().filter(annotation => !selected.has(annotation.id));
    clearSelection();
    setDirty(true);
    renderAll();
  }

  function copySelectionOrPage() {
    const annotations = selectedAnnotations();
    if (annotations.length) {
      state.clipboard = { type: 'annotations', items: clone(annotations), pasteCount: 0 };
      toast(`Copied ${annotations.length} ${annotations.length === 1 ? 'object' : 'objects'}`);
      return;
    }
    state.clipboard = { type: 'page', page: clone(currentPage()), pasteCount: 0 };
    toast(`Copied page ${state.selectedPage + 1}`);
  }

  function pasteClipboard() {
    if (!state.clipboard) {
      toast('Nothing has been copied yet.', 'warning');
      return;
    }
    checkpoint();
    if (state.clipboard.type === 'page') {
      const page = clone(state.clipboard.page);
      page.id = uid();
      page.annotations = (page.annotations || []).map(annotation => ({ ...annotation, id: uid() }));
      state.pages.splice(state.selectedPage + 1, 0, page);
      state.selectedPage += 1;
      clearSelection();
      setDirty(true);
      renderAll();
      toast(`Pasted as page ${state.selectedPage + 1}`);
      return;
    }

    state.clipboard.pasteCount += 1;
    const offset = 16 * state.clipboard.pasteCount;
    const copies = state.clipboard.items.map(annotation => {
      const copy = clone(annotation);
      copy.id = uid();
      if (copy.type === 'text') {
        copy.x += offset;
        copy.y += offset;
        if (Number.isFinite(copy.baselineY)) copy.baselineY += offset;
      } else {
        copy.points = copy.points.map(([x, y]) => [x + offset, y + offset]);
      }
      return copy;
    });
    currentAnnotations().push(...copies);
    setSelection(copies.map(copy => copy.id), copies[copies.length - 1].id);
    setDirty(true);
    renderAll();
    toast(`Pasted ${copies.length} ${copies.length === 1 ? 'object' : 'objects'}`);
  }

  function pointerDown(event) {
    if (event.button !== 0) return;
    const point = stagePoint(event);
    const targetAnnotation = annotationFromTarget(event.target);

    if (state.tool === 'select' && event.target.closest?.('.selection-resize-handle')) {
      event.preventDefault();
      startResize(point, event.pointerId);
      return;
    }

    if (state.tool === 'text') {
      event.preventDefault();
      if (targetAnnotation?.type === 'text') {
        setSelection([targetAnnotation.id], targetAnnotation.id);
        setTool('select');
        beginAnnotationEdit(targetAnnotation);
      } else addText(point);
      return;
    }
    if (state.tool === 'pen' || state.tool === 'highlight') {
      elements.stage.setPointerCapture(event.pointerId);
      startStroke(point);
      return;
    }
    if (state.tool === 'eraser') {
      const hit = targetAnnotation || hitAnnotation(point);
      if (hit) deleteAnnotation(hit.id);
      return;
    }
    if (state.tool !== 'select') return;

    if (!targetAnnotation) {
      state.lastTextClick = null;
      event.preventDefault();
      startMarquee(point, event.shiftKey, event.pointerId);
      return;
    }
    if (event.shiftKey) {
      event.preventDefault();
      const nextIds = isSelected(targetAnnotation.id)
        ? state.selectedIds.filter(id => id !== targetAnnotation.id)
        : [...state.selectedIds, targetAnnotation.id];
      setSelection(nextIds, isSelected(targetAnnotation.id) ? null : targetAnnotation.id);
      state.lastTextClick = null;
      renderStage();
      renderProperties();
      return;
    }
    const now = performance.now();
    const repeatedTextClick = targetAnnotation.type === 'text'
      && state.lastTextClick?.id === targetAnnotation.id
      && now - state.lastTextClick.time < 450;
    state.lastTextClick = targetAnnotation.type === 'text' ? { id: targetAnnotation.id, time: now } : null;
    if (repeatedTextClick) {
      event.preventDefault();
      setSelection([targetAnnotation.id], targetAnnotation.id);
      state.dragging = null;
      renderStage();
      renderProperties();
      requestAnimationFrame(() => {
        beginAnnotationEdit(targetAnnotation);
      });
      return;
    }
    if (event.target.closest?.('[contenteditable="true"]')) return;
    if (!isSelected(targetAnnotation.id)) setSelection([targetAnnotation.id], targetAnnotation.id);
    else setSelection(state.selectedIds, targetAnnotation.id);
    checkpoint();
    const annotations = selectedAnnotations();
    const originals = {};
    annotations.forEach(annotation => {
      originals[annotation.id] = annotation.type === 'text'
        ? { x: annotation.x, y: annotation.y, baselineY: annotation.baselineY }
        : { points: clone(annotation.points) };
    });
    const bounds = annotations.map(annotationBounds).filter(Boolean).reduce((combined, item) => ({
      left: Math.min(combined.left, item.left),
      top: Math.min(combined.top, item.top),
      right: Math.max(combined.right, item.right),
      bottom: Math.max(combined.bottom, item.bottom),
    }));
    state.dragging = {
      ids: annotations.map(annotation => annotation.id),
      start: point,
      originals,
      bounds,
      moved: false,
    };
    elements.stage.setPointerCapture(event.pointerId);
    renderStage();
    renderProperties();
  }

  function pointerMove(event) {
    const point = stagePoint(event);
    if (state.resizing) {
      resizeSelection(point, event.ctrlKey || event.metaKey);
      return;
    }
    if (state.marquee) {
      state.marquee.current = point;
      renderMarquee();
      return;
    }
    if (state.drawing) {
      const last = state.drawing.points[state.drawing.points.length - 1];
      if (Math.hypot(point[0] - last[0], point[1] - last[1]) > 2) {
        state.drawing.points.push(point);
        updateStrokeElement(state.drawing);
      }
      return;
    }
    if (!state.dragging) return;
    const annotations = currentAnnotations().filter(item => state.dragging.ids.includes(item.id));
    if (!annotations.length) return;
    const page = currentPage();
    const rawDx = point[0] - state.dragging.start[0];
    const rawDy = point[1] - state.dragging.start[1];
    const dx = Math.max(-state.dragging.bounds.left, Math.min(rawDx, page.width - state.dragging.bounds.right));
    const dy = Math.max(-state.dragging.bounds.top, Math.min(rawDy, page.height - state.dragging.bounds.bottom));
    state.dragging.moved = state.dragging.moved || Math.abs(dx) + Math.abs(dy) > 1;
    annotations.forEach(annotation => {
      const original = state.dragging.originals[annotation.id];
      if (annotation.type === 'text') {
        annotation.x = original.x + dx;
        annotation.y = original.y + dy;
        if (annotation.noWrap) {
          if (Number.isFinite(original.baselineY)) annotation.baselineY = original.baselineY + dy;
          updatePdfTextElement(annotation);
        } else {
          const element = elements.stage.querySelector(`.text-annotation[data-ann="${CSS.escape(annotation.id)}"]`);
          if (element) { element.style.left = `${annotation.x * state.zoom}px`; element.style.top = `${annotation.y * state.zoom}px`; }
        }
      } else {
        annotation.points = original.points.map(([x, y]) => [x + dx, y + dy]);
        updateStrokeElement(annotation);
      }
    });
  }

  function pointerUp(event) {
    if (state.resizing) {
      if (!state.resizing.moved) state.history.pop();
      else setDirty(true);
      state.resizing = null;
      renderAll();
      if (elements.stage.hasPointerCapture?.(event.pointerId)) elements.stage.releasePointerCapture(event.pointerId);
      return;
    }
    if (state.marquee) {
      finishMarquee();
      if (elements.stage.hasPointerCapture?.(event.pointerId)) elements.stage.releasePointerCapture(event.pointerId);
      return;
    }
    if (state.drawing) {
      state.drawing = null;
      renderAll();
    }
    if (state.dragging) {
      if (!state.dragging.moved) state.history.pop();
      else setDirty(true);
      state.dragging = null;
      renderAll();
    }
    if (elements.stage.hasPointerCapture?.(event.pointerId)) elements.stage.releasePointerCapture(event.pointerId);
  }

  function updateSelectedProperty(property, value, checkpointFirst = true) {
    const annotations = selectedAnnotations().filter(annotation => {
      if (["fontSize", "bold", "cover"].includes(property)) return annotation.type === 'text';
      if (property === 'lineWidth') return annotation.type === 'stroke';
      return true;
    });
    if (!annotations.length) return;
    if (checkpointFirst) checkpoint();
    annotations.forEach(annotation => { annotation[property] = value; });
    const primary = selectedAnnotation() || annotations[0];
    const defaults = primary.type === 'text' ? state.defaults.text : primary.tool === 'highlight' ? state.defaults.highlight : state.defaults.pen;
    if (property in defaults) defaults[property] = value;
    setDirty(true);
    renderStage();
    renderProperties();
  }

  function addBlankPage() {
    checkpoint();
    state.pages.splice(state.selectedPage + 1, 0, makeBlankPage());
    state.selectedPage += 1;
    clearSelection();
    setDirty(true);
    renderAll();
    fitPage();
  }

  function duplicatePage() {
    checkpoint();
    const copy = { ...currentPage(), id: uid(), annotations: clone(currentPage().annotations).map(annotation => ({ ...annotation, id: uid() })) };
    state.pages.splice(state.selectedPage + 1, 0, copy);
    state.selectedPage += 1;
    clearSelection();
    setDirty(true);
    renderAll();
  }

  function deletePage() {
    if (state.pages.length <= 1) return;
    checkpoint();
    state.pages.splice(state.selectedPage, 1);
    state.selectedPage = Math.min(state.selectedPage, state.pages.length - 1);
    clearSelection();
    setDirty(true);
    renderAll();
  }

  function setZoom(value) {
    state.zoom = Math.max(0.2, Math.min(2, value));
    renderStage();
    updateStatus();
  }

  function fitPage() {
    const page = currentPage();
    if (!page) return;
    const rect = elements.scroller.getBoundingClientRect();
    const availableWidth = Math.max(200, rect.width - 110);
    const availableHeight = Math.max(250, rect.height - 90);
    setZoom(Math.min(1, availableWidth / page.width, availableHeight / page.height));
  }

  async function openFile(file) {
    if (!file) return;
    if (file.name.toLowerCase().endsWith('.pdfeditorathome')) {
      await openProject(file);
      return;
    }
    showBusy('Opening document…', 'Converting pages locally');
    try {
      const form = new FormData();
      form.append('file', file);
      const response = await fetch('/api/import', { method: 'POST', body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Could not open the file.');
      state.name = data.name || 'Untitled document';
      state.documentId = data.documentId;
      state.sourceFormat = data.sourceFormat;
      state.pages = data.pages.map((page, index) => ({
        id: uid(), width: page.width, height: page.height,
        imageUrl: page.imageUrl, imageData: null,
        documentId: data.documentId, serverIndex: page.serverIndex ?? index,
        annotations: (page.annotations || []).map(annotation => ({ ...annotation, id: annotation.id || uid() })),
      }));
      state.selectedPage = 0;
      clearSelection();
      state.history = [];
      state.future = [];
      elements.title.value = state.name;
      setDirty(false);
      renderAll();
      requestAnimationFrame(fitPage);
      if (data.sourceFormat === 'pdf' && !data.editableTextCount) {
        toast(`Opened ${file.name}, but no selectable text was found. Scanned pages require OCR.`, 'warning');
      } else {
        const detail = data.editableTextCount ? ` — ${data.editableTextCount} editable text ${data.editableTextCount === 1 ? 'box' : 'boxes'}` : '';
        toast(`Opened ${file.name}${detail}`);
      }
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      hideBusy();
      elements.fileInput.value = '';
    }
  }

  async function openProject(file) {
    showBusy('Opening project…', 'Restoring editable layers');
    try {
      const data = JSON.parse(await file.text());
      if (data.format !== projectFormat || !Array.isArray(data.pages) || !data.pages.length) throw new Error('This is not a valid PDFeditorAthome project.');
      state.name = data.name || file.name.replace(/\.pdfeditorathome$/i, '');
      state.documentId = null;
      state.sourceFormat = data.format;
      state.pages = data.pages.map(page => ({
        id: uid(), width: Number(page.width), height: Number(page.height),
        imageData: page.imageData, imageUrl: null, documentId: null, serverIndex: null,
        annotations: (page.annotations || []).map(annotation => ({ ...annotation, id: uid() })),
      }));
      state.selectedPage = 0;
      clearSelection();
      state.history = [];
      state.future = [];
      elements.title.value = state.name;
      setDirty(false);
      renderAll();
      requestAnimationFrame(fitPage);
      toast('Project restored');
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      hideBusy();
      elements.fileInput.value = '';
    }
  }

  function blobToDataUrl(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(blob);
    });
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function exportProject() {
    const pages = [];
    for (const page of state.pages) {
      let imageData = page.imageData;
      if (!imageData) {
        const response = await fetch(page.imageUrl);
        if (!response.ok) throw new Error('A page image is no longer available. Reopen the source document.');
        imageData = await blobToDataUrl(await response.blob());
      }
      pages.push({ width: page.width, height: page.height, imageData, annotations: page.annotations });
    }
    const project = { format: projectFormat, version: 1, name: state.name, createdAt: new Date().toISOString(), pages };
    downloadBlob(new Blob([JSON.stringify(project)], { type: 'application/json' }), `${safeFilename(state.name)}.pdfeditorathome`);
  }

  function safeFilename(value) {
    return (value || 'edited-document').replace(/[\\/:*?"<>|]/g, '').trim() || 'edited-document';
  }

  async function exportDocument() {
    const format = $('input[name="format"]:checked', elements.exportDialog)?.value || 'pdf';
    elements.exportDialog.close();
    showBusy('Exporting document…', format === projectFormat ? 'Packing editable pages' : `Creating ${format.toUpperCase()} locally`);
    elements.confirmExportButton.disabled = true;
    try {
      if (format === projectFormat) {
        await exportProject();
      } else {
        const response = await fetch('/api/export', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: state.name, format, pageIndex: state.selectedPage,
            pages: state.pages.map(page => ({
              width: page.width, height: page.height,
              documentId: page.documentId, serverIndex: page.serverIndex,
              imageData: page.imageData, annotations: page.annotations,
            })),
          }),
        });
        if (!response.ok) {
          const data = await response.json().catch(() => ({}));
          throw new Error(data.error || 'Export failed.');
        }
        downloadBlob(await response.blob(), `${safeFilename(state.name)}.${format}`);
      }
      setDirty(false);
      toast(`${format.toUpperCase()} exported`);
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      hideBusy();
      elements.confirmExportButton.disabled = false;
    }
  }

  function openExportDialog() {
    if (!elements.exportDialog.open) elements.exportDialog.showModal();
  }

  elements.openButton.addEventListener('click', () => elements.fileInput.click());
  elements.fileInput.addEventListener('change', () => openFile(elements.fileInput.files[0]));
  elements.exportButton.addEventListener('click', openExportDialog);
  elements.confirmExportButton.addEventListener('click', exportDocument);
  elements.addPageButton.addEventListener('click', addBlankPage);
  elements.duplicatePageButton.addEventListener('click', duplicatePage);
  elements.deletePageButton.addEventListener('click', deletePage);
  elements.undoButton.addEventListener('click', undo);
  elements.redoButton.addEventListener('click', redo);
  elements.zoomOutButton.addEventListener('click', () => setZoom(state.zoom - 0.1));
  elements.zoomInButton.addEventListener('click', () => setZoom(state.zoom + 0.1));
  elements.zoomLabel.addEventListener('click', fitPage);
  elements.toolGroup.addEventListener('click', event => {
    const button = event.target.closest('[data-tool]');
    if (button) setTool(button.dataset.tool);
  });
  elements.stage.addEventListener('pointerdown', pointerDown);
  elements.stage.addEventListener('pointermove', pointerMove);
  elements.stage.addEventListener('pointerup', pointerUp);
  elements.stage.addEventListener('pointercancel', pointerUp);
  elements.stage.addEventListener('dblclick', event => {
    const annotation = annotationFromTarget(event.target);
    if (annotation?.type === 'text') {
      setSelection([annotation.id], annotation.id);
      setTool('select');
      beginAnnotationEdit(annotation);
    }
  });
  elements.stage.addEventListener('input', event => {
    const element = event.target.closest?.('.text-annotation');
    if (!element) return;
    const annotation = currentAnnotations().find(item => item.id === element.dataset.ann);
    if (!annotation) return;
    if (element.dataset.editStarted === 'false') {
      checkpoint();
      element.dataset.editStarted = 'true';
    }
    const badge = $('.selection-badge', element);
    if (badge) badge.remove();
    annotation.text = element.innerText;
    if (annotation.noWrap) {
      annotation.width = Math.ceil(measureTextAnnotation(annotation, annotation.text) + 2);
      annotation.height = Math.max(annotation.fontSize * 1.2, annotation.text.split('\n').length * annotation.fontSize * 1.15);
      element.style.width = `${annotation.width * state.zoom}px`;
    } else {
      annotation.height = Math.max(30, element.offsetHeight / state.zoom);
    }
    setDirty(true);
  });
  elements.stage.addEventListener('focusout', event => {
    const element = event.target.closest?.('.text-annotation');
    if (!element) return;
    element.contentEditable = 'false';
    renderAll();
  });

  elements.colorInput.addEventListener('change', event => updateSelectedProperty('color', event.target.value));
  $$('.swatches button').forEach(button => button.addEventListener('click', () => updateSelectedProperty('color', button.dataset.color)));
  elements.fontSizeInput.addEventListener('change', event => updateSelectedProperty('fontSize', Math.max(8, Math.min(120, Number(event.target.value) || 24))));
  elements.boldButton.addEventListener('click', () => updateSelectedProperty('bold', !selectedAnnotation()?.bold));
  elements.coverButton.addEventListener('click', () => updateSelectedProperty('cover', !selectedAnnotation()?.cover));
  elements.lineWidthInput.addEventListener('pointerdown', () => { state.propertyCheckpointed = false; });
  elements.lineWidthInput.addEventListener('input', event => {
    if (!state.propertyCheckpointed) { checkpoint(); state.propertyCheckpointed = true; }
    updateSelectedProperty('lineWidth', Number(event.target.value), false);
  });
  elements.opacityInput.addEventListener('pointerdown', () => { state.propertyCheckpointed = false; });
  elements.opacityInput.addEventListener('input', event => {
    if (!state.propertyCheckpointed) { checkpoint(); state.propertyCheckpointed = true; }
    updateSelectedProperty('opacity', Number(event.target.value) / 100, false);
  });
  elements.duplicateSelectionButton.addEventListener('click', duplicateSelection);
  elements.deleteSelectionButton.addEventListener('click', deleteSelection);
  elements.title.addEventListener('focus', () => { elements.title.dataset.before = state.name; });
  elements.title.addEventListener('change', () => {
    const next = elements.title.value.trim() || 'Untitled document';
    if (next !== state.name) {
      checkpoint();
      state.name = next;
      elements.title.value = next;
      setDirty(true);
    }
  });

  elements.formatGrid.addEventListener('change', () => {
    $$('.format-card', elements.formatGrid).forEach(card => card.classList.toggle('selected', $('input', card).checked));
  });

  let dragDepth = 0;
  window.addEventListener('dragenter', event => {
    if (!event.dataTransfer?.types.includes('Files')) return;
    event.preventDefault();
    dragDepth += 1;
    elements.dropHint.hidden = false;
  });
  window.addEventListener('dragover', event => event.preventDefault());
  window.addEventListener('dragleave', event => {
    event.preventDefault();
    dragDepth -= 1;
    if (dragDepth <= 0) { dragDepth = 0; elements.dropHint.hidden = true; }
  });
  window.addEventListener('drop', event => {
    event.preventDefault();
    dragDepth = 0;
    elements.dropHint.hidden = true;
    openFile(event.dataTransfer?.files[0]);
  });

  document.addEventListener('keydown', event => {
    const editingText = event.target.closest?.('[contenteditable="true"]');
    const editingInput = /INPUT|TEXTAREA|SELECT/.test(event.target.tagName);
    const modifier = event.ctrlKey || event.metaKey;
    if (modifier && event.key.toLowerCase() === 'o') { event.preventDefault(); elements.fileInput.click(); return; }
    if (modifier && event.key.toLowerCase() === 's') { event.preventDefault(); openExportDialog(); return; }
    if (modifier && event.key.toLowerCase() === 'z') { event.preventDefault(); event.shiftKey ? redo() : undo(); return; }
    if (modifier && event.key.toLowerCase() === 'y') { event.preventDefault(); redo(); return; }
    if (editingText || editingInput) return;
    if (modifier && event.key.toLowerCase() === 'c') { event.preventDefault(); copySelectionOrPage(); return; }
    if (modifier && event.key.toLowerCase() === 'v') { event.preventDefault(); pasteClipboard(); return; }
    if (modifier && event.key.toLowerCase() === 'a') {
      event.preventDefault();
      const ids = currentAnnotations().map(annotation => annotation.id);
      setSelection(ids, ids[ids.length - 1]);
      renderStage();
      renderProperties();
      return;
    }
    if (event.key === 'Delete') {
      event.preventDefault();
      if (selectedAnnotations().length) deleteSelection();
      else deletePage();
      return;
    }
    if (event.key === 'Backspace' && selectedAnnotations().length) {
      event.preventDefault();
      deleteSelection();
      return;
    }
    if (modifier && event.key.toLowerCase() === 'd' && selectedAnnotations().length) { event.preventDefault(); duplicateSelection(); return; }
    const tools = { v: 'select', t: 'text', p: 'pen', h: 'highlight', e: 'eraser' };
    if (!modifier && tools[event.key.toLowerCase()]) setTool(tools[event.key.toLowerCase()]);
    if (event.key === '+' || event.key === '=') setZoom(state.zoom + 0.1);
    if (event.key === '-') setZoom(state.zoom - 0.1);
    if (event.key === 'Escape') { clearSelection(); setTool('select'); }
  });

  window.addEventListener('beforeunload', event => {
    if (!state.dirty) return;
    event.preventDefault();
    event.returnValue = '';
  });
  window.addEventListener('resize', () => {
    if (window.innerWidth < 720) fitPage();
  });

  state.pages = [makeBlankPage()];
  renderAll();
  requestAnimationFrame(fitPage);
})();
