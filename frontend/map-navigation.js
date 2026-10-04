/* Keep every map layer on one camera while dragging or zooming the canvas. */
(() => {
  'use strict';

  window.attachMapNavigation = (canvas, {
    getView,
    setView,
    minScale = .12,
    maxScale = 1.6,
    getScaleLimits = () => ({minScale, maxScale})
  }) => {
    const pointers = new Map();
    let gesture = null;
    const clampScale = scale => {
      const limits = getScaleLimits();
      return Math.min(limits.maxScale, Math.max(limits.minScale, scale));
    };
    const position = event => {
      const rect = canvas.getBoundingClientRect();
      return {
        x: (event.clientX - rect.left) * canvas.width / Math.max(1, rect.width),
        y: (event.clientY - rect.top) * canvas.height / Math.max(1, rect.height)
      };
    };
    const midpoint = (a, b) => ({x: (a.x + b.x) / 2, y: (a.y + b.y) / 2});
    const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
    const restingCursor = canvas.style.cursor || 'grab';
    canvas.style.touchAction = 'none';
    canvas.style.cursor = restingCursor;

    function rebaseGesture() {
      const ids = [...pointers.keys()].slice(0, 2);
      canvas.style.cursor = ids.length ? 'grabbing' : restingCursor;
      if (!ids.length) {
        gesture = null;
        return;
      }
      const first = pointers.get(ids[0]);
      const second = pointers.get(ids[1]);
      const center = second ? midpoint(first, second) : first;
      const view = getView();
      gesture = {
        ids,
        view: {scale: view.scale, x: view.x, y: view.y},
        center: {...center},
        distance: second ? distance(first, second) : 0,
        anchor: {
          x: (center.x - view.x) / view.scale,
          y: (center.y - view.y) / view.scale
        }
      };
    }

    function resetInteraction() {
      const ids = [...pointers.keys()];
      pointers.clear();
      rebaseGesture();
      for (const id of ids) {
        if (canvas.hasPointerCapture?.(id)) canvas.releasePointerCapture(id);
      }
    }

    canvas.addEventListener('wheel', event => {
      event.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? rect.height : 1);
      if (!delta) return;
      const point = position(event);
      const view = getView();
      const scale = clampScale(view.scale * Math.exp(-delta * .0015));
      const ratio = scale / view.scale;
      setView({
        scale,
        x: point.x - (point.x - view.x) * ratio,
        y: point.y - (point.y - view.y) * ratio
      });
      if (pointers.size) rebaseGesture();
    }, {passive: false});

    canvas.addEventListener('pointerdown', event => {
      if (event.pointerType === 'mouse' && event.button !== 0) return;
      event.preventDefault();
      pointers.set(event.pointerId, position(event));
      rebaseGesture();
      // Capture keeps a drag attached when it passes beyond the canvas bounds.
      try { canvas.setPointerCapture(event.pointerId); } catch (_) { /* Synthetic pointer events have no capture. */ }
    });

    canvas.addEventListener('pointermove', event => {
      if (!pointers.has(event.pointerId)) return;
      event.preventDefault();
      pointers.set(event.pointerId, position(event));
      const first = pointers.get(gesture.ids[0]);
      const second = pointers.get(gesture.ids[1]);
      if (second) {
        const center = midpoint(first, second);
        // Coincident touches establish a fresh baseline once they separate.
        if (gesture.distance < 1) {
          rebaseGesture();
          return;
        }
        const scale = clampScale(gesture.view.scale * distance(first, second) / gesture.distance);
        setView({
          scale,
          x: center.x - gesture.anchor.x * scale,
          y: center.y - gesture.anchor.y * scale
        });
      } else {
        setView({
          scale: gesture.view.scale,
          x: gesture.view.x + first.x - gesture.center.x,
          y: gesture.view.y + first.y - gesture.center.y
        });
      }
    });

    function endPointer(event) {
      if (!pointers.delete(event.pointerId)) return;
      rebaseGesture();
      if (canvas.hasPointerCapture?.(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    }
    canvas.addEventListener('pointerup', endPointer);
    canvas.addEventListener('pointercancel', endPointer);
    canvas.addEventListener('lostpointercapture', endPointer);
    window.addEventListener('blur', resetInteraction);

    return {resetInteraction};
  };
})();
