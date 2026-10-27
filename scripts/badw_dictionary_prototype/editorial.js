'use strict';
(async function () {
  const index = document.getElementById('documents');
  const article = document.getElementById('article');
  const element = (tag, text, parent) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (parent) parent.append(node);
    return node;
  };
  try {
    const response = await fetch('collection.json');
    if (!response.ok) throw new Error('Collection could not be loaded.');
    const collection = await response.json();
    index.replaceChildren();
    for (const memorial of [false, true]) {
      element('h2', memorial ? 'Related memorial texts' : 'Prefaces and introductions', index);
      for (const doc of collection.documents.filter(d => (d.category === 'Memorial') === memorial)) {
        const link = element('a', `${doc.volume} · ${doc.title}`, index);
        link.href = '#' + encodeURIComponent(doc.id);
        link.dataset.document = doc.id;
      }
    }
    function render() {
      let id;
      try { id = decodeURIComponent(location.hash.slice(1)); } catch { id = ''; }
      const doc = collection.documents.find(d => d.id === id) || collection.documents[0];
      article.replaceChildren();
      const title = element('h2', doc.title, article);
      title.lang = 'de'; title.tabIndex = -1;
      element('p', `${doc.volume} · ${doc.category}`, article);
      element('p', doc.authors.length ? doc.authors.join('; ') : 'Authorship not established in the reviewed inventory.', article);
      if (doc.subject) element('p', doc.subject, article);
      for (const section of doc.sections) {
        const block = element('section', undefined, article); block.className = 'editorial-section';
        element('h3', 'Printed page ' + section.views.map(v => v.folio).join('–'), block);
        element('p', section.reading_status === 'verified_editorial_transcription' ? 'Reviewed transcription recorded in the source inventory.' : 'Unreviewed OCR · spelling, layout and reading order may contain errors.', block);
        const links = element('p', undefined, block);
        for (const view of section.views) {
          if (!/^pages\/[a-f0-9]{64}\.pdf$/.test(view.url)) throw new Error('Unsafe source link');
          const link = element('a', `Original printed page ${view.folio}`, links);
          link.href = view.url + '#page=1&view=Fit'; link.target = '_blank'; link.rel = 'noopener';
          links.append(document.createTextNode(' · '));
        }
        const text = element('div', section.text, block); text.className = 'editorial-text'; text.lang = 'de';
        const provenance = element('details', undefined, block);
        element('summary', 'Source information', provenance);
        element('pre', JSON.stringify({source: section.source_label, physical_pdf_page: section.physical_page, ocr_sha256: section.ocr_sha256, source_span: section.source_span, raw_span_sha256: section.raw_span_sha256, views: section.views}, null, 2), provenance);
      }
      for (const link of index.querySelectorAll('a')) {
        if (link.dataset.document === doc.id) link.setAttribute('aria-current', 'page');
        else link.removeAttribute('aria-current');
      }
    }
    window.addEventListener('hashchange', () => { render(); article.focus(); });
    render();
  } catch (error) {
    article.textContent = 'Unable to display the editorial collection: ' + error.message;
  }
})();
