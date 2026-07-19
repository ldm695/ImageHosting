(function() {
  'use strict';

  var AC = window.APP_CONFIG || {};

  // ── Theme ────────────────────────────────────

  var _themeMode = 'auto';  // auto | light | dark
  var _systemDark = window.matchMedia('(prefers-color-scheme: dark)');

  function resolveTheme(mode) {
    if (mode === 'auto') return _systemDark.matches ? 'dark' : 'light';
    return mode;
  }

  function applyTheme(mode) {
    _themeMode = mode;
    document.documentElement.setAttribute('data-theme', resolveTheme(mode));
  }

  // Apply initial theme immediately — server value first, then localStorage, default auto
  (function() {
    var init = AC.theme;
    if (!init) {
      try { init = localStorage.getItem('imagehosting_theme'); } catch(e) {}
    }
    applyTheme(init || 'auto');
  })();

  // Listen to system preference changes (for auto mode)
  _systemDark.addEventListener('change', function() {
    if (_themeMode === 'auto') applyTheme('auto');
  });

  // ── State ────────────────────────────────────

  const DEFAULT_GROUP = AC.defaultGroup || 'general';
  let currentGroup = DEFAULT_GROUP;
  let images = [];
  let currentIndex = -1;
  let isLoading = false;
  let isSelectMode = false;
  let selectedSet = new Set();
  let searchQuery = '';
  let pendingUploadFiles = null;
  let allImages = [];
  let sortMode = 'name';
  let sortAsc = true;
  let tagFilter = null;
  let allTags = [];

  // ── DOM refs ─────────────────────────────────

  const $ = id => document.getElementById(id);

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  const grid = $('imageGrid');
  const emptyState = $('emptyState');
  const imageCount = $('imageCount');
  const uploadZone = $('uploadZone');
  const fileInput = $('fileInput');
  const uploadProgress = $('uploadProgress');
  const progressFill = $('progressFill');
  const progressText = $('progressText');

  const lightbox = $('lightbox');
  const lightboxImg = $('lightboxImg');
  const lbFilename = $('lbFilename');
  const lbMeta = $('lbMeta');
  const lbDelete = $('lbDelete');
  const lightboxClose = $('lightboxClose');
  const lightboxPrev = $('lightboxPrev');
  const lightboxNext = $('lightboxNext');
  const lbTagArea = $('lbTagArea');
  const lbTag = $('lbTag');
  const lbTagBtn = $('lbTagBtn');
  const lbTagEditor = $('lbTagEditor');
  const lbTagInput = $('lbTagInput');
  const lbTagSuggestions = $('lbTagSuggestions');
  const lbTagSave = $('lbTagSave');
  const lbTagClear = $('lbTagClear');

  const confirmDialog = $('confirmDialog');
  const confirmText = $('confirmText');
  const confirmCancel = $('confirmCancel');
  const confirmOk = $('confirmOk');

  const createGroupDialog = $('createGroupDialog');
  const newGroupInput = $('newGroupInput');
  const createGroupCancel = $('createGroupCancel');
  const createGroupOk = $('createGroupOk');

  const groupSelect = $('groupSelect');
  const groupTrigger = $('groupTrigger');
  const groupMenu = $('groupMenu');
  const groupArrow = $('groupArrow');
  const currentGroupLabel = $('currentGroupLabel');

  const snackbarContainer = $('snackbarContainer');

  const lbRename = $('lbRename');
  const lbMove = $('lbMove');
  const renameDialog = $('renameDialog');
  const renameInput = $('renameInput');
  const renameCancel = $('renameCancel');
  const renameOk = $('renameOk');
  const moveDialog = $('moveDialog');
  const moveFilenameLabel = $('moveFilenameLabel');
  const moveGroupList = $('moveGroupList');
  const moveCancel = $('moveCancel');
  const moveOk = $('moveOk');

  const selectToggle = $('selectToggle');
  const toolbarSelect = $('toolbarSelect');
  const selectCount = $('selectCount');
  const selectCancel = $('selectCancel');
  const selectAllBtn = $('selectAllBtn');
  const batchMoveBtn = $('batchMoveBtn');
  const batchDeleteBtn = $('batchDeleteBtn');
  const batchTagBtn = $('batchTagBtn');
  const batchTagDialog = $('batchTagDialog');
  const batchTagCount = $('batchTagCount');
  const batchTagInput = $('batchTagInput');
  const batchTagSuggestions = $('batchTagSuggestions');
  const batchTagCancel = $('batchTagCancel');
  const batchTagOk = $('batchTagOk');
  const tagSelect = $('tagSelect');
  const tagTrigger = $('tagTrigger');
  const tagMenu = $('tagMenu');
  const tagSelectLabel = $('tagSelectLabel');
  const tagSelectCount = $('tagSelectCount');
  const manageTagsBtn = $('manageTagsBtn');
  const manageTagsDialog = $('manageTagsDialog');
  const manageTagsList = $('manageTagsList');
  const manageTagsClose = $('manageTagsClose');
  const renameTagDialog = $('renameTagDialog');
  const renameTagInput = $('renameTagInput');
  const renameTagHint = $('renameTagHint');
  const renameTagCancel = $('renameTagCancel');
  const renameTagOk = $('renameTagOk');
  const uploadRenameDialog = $('uploadRenameDialog');
  const uploadFileList = $('uploadFileList');
  const uploadRenameCancel = $('uploadRenameCancel');
  const uploadRenameOk = $('uploadRenameOk');

  const searchInput = $('searchInput');
  const searchClear = $('searchClear');
  const searchSuggestions = $('searchSuggestions');
  const sortTrigger = $('sortTrigger');
  const sortLabel = $('sortLabel');
  const sortMenu = $('sortMenu');
  const sortArrow = document.querySelector('.sort-select__arrow');

  const settingsBtn = $('settingsBtn');
  const settingsDialog = $('settingsDialog');
  const settingsDataDir = $('settingsDataDir');
  const settingsCancel = $('settingsCancel');
  const settingsError = $('settingsError');
  const settingsSave = $('settingsSave');
  const settingsTimeout = $('settingsTimeout');
  const settingsPort = $('settingsPort');
  const browseBtn = $('browseBtn');
  const allowedPortInput = $('allowedPortInput');
  const allowedPortAdd = $('allowedPortAdd');
  const allowedPortsList = $('allowedPortsList');

  let pendingDelete = null;
  let pendingDeleteGroup = null;
  let pendingDeleteTag = null;
  var _initTheme = 'auto';
  let _initDir = '';
  let _initTimeoutSec = 300;
  let _initPort = 6951;
  let _allowedPorts = [];
  let _initAllowedPorts = [];

  // ── Snackbar ─────────────────────────────────

  const SNACKBAR_ICONS = {
    success: 'check_circle',
    error: 'error',
    info: 'info',
  };

  function snackbar(message, type) {
    if (type === undefined) type = 'info';
    const icon = SNACKBAR_ICONS[type] || 'info';
    const el = document.createElement('div');
    el.className = 'snackbar snackbar--' + type;
    el.innerHTML = '<span class="material-symbols-outlined snackbar__icon">' + icon + '</span><span>' + message + '</span>';
    snackbarContainer.appendChild(el);
    setTimeout(function() {
      el.style.transition = 'opacity 0.3s, transform 0.3s';
      el.style.opacity = '0';
      el.style.transform = 'translateY(16px) scale(0.95)';
      setTimeout(function() { el.remove(); }, 300);
    }, 3000);
  }

  // ── Group API ─────────────────────────────────

  async function loadGroups() {
    try {
      const res = await fetch('/api/groups');
      const groups = await res.json();
      renderGroupMenu(groups);
      return groups;
    } catch (err) {
      snackbar('Failed to load groups: ' + err.message, 'error');
      return [];
    }
  }

  function renderGroupMenu(groups) {
    var html = '';
    for (const g of groups) {
      const isActive = g.name === currentGroup;
      const isDefault = g.name === DEFAULT_GROUP;
      html += '\
        <div class="group-select__item ' + (isActive ? 'active' : '') + '"\
             data-group="' + g.name + '">\
          <span class="material-symbols-outlined group-select__item-icon">folder</span>\
          <span class="group-select__item-name">' + g.name + '</span>\
          <span class="group-select__item-count">' + g.count + '</span>\
          <span class="material-symbols-outlined group-select__item-check">check</span>\
          ' + (!isDefault ? '<button class="group-select__item-delete" data-group="' + g.name + '" title="Delete group">\
            <span class="material-symbols-outlined" style="font-size:1rem;">delete</span>\
          </button>' : '') + '\
        </div>';
    }
    html += '\
      <div class="group-select__divider"></div>\
      <div class="group-select__new" id="groupNewBtn">\
        <span class="material-symbols-outlined">add</span>\
        <span>New Group</span>\
      </div>';
    groupMenu.innerHTML = html;

    groupMenu.querySelectorAll('.group-select__item').forEach(function(el) {
      el.addEventListener('click', function(e) {
        if (e.target.closest('.group-select__item-delete')) return;
        var name = el.dataset.group;
        if (name !== currentGroup) switchGroup(name);
        closeGroupMenu();
      });
    });

    groupMenu.querySelectorAll('.group-select__item-delete').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        promptDeleteGroup(btn.dataset.group);
      });
    });

    var newBtn = groupMenu.querySelector('#groupNewBtn');
    if (newBtn) {
      newBtn.addEventListener('click', function() {
        closeGroupMenu();
        openCreateGroupDialog();
      });
    }
  }

  async function switchGroup(name) {
    if (name === currentGroup) return;
    if (isSelectMode) exitSelectMode();
    if (searchQuery) {
      searchInput.value = '';
      searchQuery = '';
    }
    sortMode = 'name';
    sortAsc = true;
    sortLabel.textContent = 'Name';
    tagFilter = null;
    allTags = [];
    currentGroup = name;
    currentGroupLabel.textContent = name;
    closeGroupMenu();
    await loadImages();
    loadGroups();
  }

  async function createGroup(name) {
    try {
      const res = await fetch('/api/groups', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name }),
      });
      const data = await res.json();
      if (data.error) {
        snackbar(data.error, 'error');
        return false;
      }
      snackbar('Created group "' + name + '"', 'success');
      await loadGroups();
      await switchGroup(name);
      return true;
    } catch (err) {
      snackbar('Failed to create group: ' + err.message, 'error');
      return false;
    }
  }

  async function deleteGroup(name) {
    try {
      const res = await fetch('/api/groups/' + encodeURIComponent(name), {
        method: 'DELETE',
      });
      const data = await res.json();
      if (data.error) {
        snackbar(data.error, 'error');
        return false;
      }
      snackbar('Deleted group "' + name + '"', 'success');
      if (currentGroup === name) {
        await switchGroup(DEFAULT_GROUP);
      } else {
        await loadGroups();
      }
      return true;
    } catch (err) {
      snackbar('Failed to delete group: ' + err.message, 'error');
      return false;
    }
  }

  function promptDeleteGroup(name) {
    pendingDeleteGroup = name;
    confirmText.textContent = 'Delete group "' + name + '" and all its images? This cannot be undone.';
    confirmDialog.classList.add('active');
  }

  // ── Group UI ──────────────────────────────────

  function toggleGroupMenu() {
    if (groupMenu.classList.contains('open')) {
      closeGroupMenu();
    } else {
      openGroupMenu();
    }
  }

  function openGroupMenu() {
    groupMenu.classList.add('open');
    groupArrow.classList.add('open');
    loadGroups();
  }

  function closeGroupMenu() {
    groupMenu.classList.remove('open');
    groupArrow.classList.remove('open');
  }

  groupTrigger.addEventListener('click', toggleGroupMenu);

  document.addEventListener('click', function(e) {
    if (!groupSelect.contains(e.target)) {
      closeGroupMenu();
    }
  });

  // ── Create Group Dialog ───────────────────────

  function openCreateGroupDialog() {
    newGroupInput.value = '';
    createGroupDialog.classList.add('active');
    setTimeout(function() { newGroupInput.focus(); }, 100);
  }

  function closeCreateGroupDialog() {
    createGroupDialog.classList.remove('active');
  }

  createGroupCancel.addEventListener('click', closeCreateGroupDialog);
  createGroupOk.addEventListener('click', async function() {
    var name = newGroupInput.value.trim();
    if (!name) {
      snackbar('Please enter a group name', 'error');
      return;
    }
    closeCreateGroupDialog();
    await createGroup(name);
  });

  newGroupInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') createGroupOk.click();
    if (e.key === 'Escape') closeCreateGroupDialog();
  });

  createGroupDialog.addEventListener('click', function(e) {
    if (e.target === createGroupDialog) closeCreateGroupDialog();
  });

  // ── Load Images ───────────────────────────────

  async function loadImages() {
    if (isLoading) return;
    isLoading = true;
    try {
      var url = '/api/images?group=' + encodeURIComponent(currentGroup);
      if (tagFilter) url += '&tag=' + encodeURIComponent(tagFilter);
      const res = await fetch(url);
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      allImages = data.images || [];
      allTags = data.tags || [];
      applyFilter();
      renderTagChips();
    } catch (err) {
      snackbar('Failed to load: ' + err.message, 'error');
    } finally {
      isLoading = false;
    }
  }

  // ── Search / Filter ────────────────────────────

  function applyFilter() {
    var q = searchQuery.trim().toLowerCase();
    var filtered = !q
      ? [...allImages]
      : allImages.filter(function(img) {
          var nameMatch = img.filename.toLowerCase().includes(q);
          var tagMatch = (img.tag || '').toLowerCase().includes(q);
          return nameMatch || tagMatch;
        });
    filtered.sort(function(a, b) {
      var cmp;
      if (sortMode === 'name') {
        cmp = a.filename.localeCompare(b.filename);
      } else {
        cmp = new Date(a.created) - new Date(b.created);
      }
      return sortAsc ? cmp : -cmp;
    });
    images = filtered;
    renderGrid();
  }

  function showSuggestions() {
    var q = searchInput.value.trim().toLowerCase();
    if (!q || allImages.length === 0) {
      searchSuggestions.classList.remove('open');
      return;
    }

    var matches = allImages
      .filter(function(img) { return img.filename.toLowerCase().includes(q); })
      .slice(0, 10);

    if (matches.length === 0) {
      searchSuggestions.classList.remove('open');
      return;
    }

    var re = new RegExp('(' + q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
    var html = '';
    for (const m of matches) {
      var highlighted = m.filename.replace(re, '<mark>$1</mark>');
      html += '\
        <div class="search-suggestion" data-filename="' + m.filename + '">\
          <span class="material-symbols-outlined suggestion-icon">image</span>\
          <span class="suggestion-name">' + highlighted + '</span>\
          <span class="suggestion-meta">' + (m.formatted_size || '') + '</span>\
        </div>';
    }
    searchSuggestions.innerHTML = html;
    searchSuggestions.classList.add('open');

    searchSuggestions.querySelectorAll('.search-suggestion').forEach(function(el) {
      el.addEventListener('click', function() {
        searchInput.value = el.dataset.filename;
        searchSuggestions.classList.remove('open');
        searchQuery = el.dataset.filename;
        applyFilter();
        searchInput.focus();
      });
    });
  }

  function hideSuggestions() {
    searchSuggestions.classList.remove('open');
  }

  searchInput.addEventListener('input', function() {
    searchQuery = searchInput.value;
    applyFilter();
    showSuggestions();
  });

  searchInput.addEventListener('focus', function() {
    if (searchInput.value.trim()) showSuggestions();
  });

  searchInput.addEventListener('keydown', function(e) {
    var suggestions = searchSuggestions.querySelectorAll('.search-suggestion');
    if (!suggestions.length) return;

    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      var active = searchSuggestions.querySelector('.search-suggestion.active');
      var next;
      if (!active) {
        next = e.key === 'ArrowDown' ? suggestions[0] : suggestions[suggestions.length - 1];
      } else {
        var idx = Array.from(suggestions).indexOf(active);
        next = e.key === 'ArrowDown'
          ? suggestions[Math.min(idx + 1, suggestions.length - 1)]
          : suggestions[Math.max(idx - 1, 0)];
      }
      if (active) active.classList.remove('active');
      next.classList.add('active');
      next.scrollIntoView({ block: 'nearest' });
    }

    if (e.key === 'Enter') {
      var activeEnter = searchSuggestions.querySelector('.search-suggestion.active');
      if (activeEnter) {
        e.preventDefault();
        searchInput.value = activeEnter.dataset.filename;
        hideSuggestions();
        searchQuery = activeEnter.dataset.filename;
        applyFilter();
      }
    }

    if (e.key === 'Escape') hideSuggestions();
  });

  searchClear.addEventListener('click', function() {
    searchInput.value = '';
    searchQuery = '';
    hideSuggestions();
    applyFilter();
    searchInput.focus();
  });

  document.addEventListener('click', function(e) {
    if (!e.target.closest('.search-box')) {
      hideSuggestions();
    }
  });

  // ── Sort ───────────────────────────────────────

  var SORT_OPTIONS = [
    { mode: 'name', asc: true, label: 'Name A–Z', icon: 'sort_by_alpha' },
    { mode: 'name', asc: false, label: 'Name Z–A', icon: 'sort_by_alpha' },
    { mode: 'time', asc: false, label: 'Newest first', icon: 'schedule' },
    { mode: 'time', asc: true, label: 'Oldest first', icon: 'schedule' },
  ];

  function renderSortMenu() {
    sortMenu.innerHTML = SORT_OPTIONS.map(function(opt) {
      var active = opt.mode === sortMode && opt.asc === sortAsc;
      return '\
        <div class="sort-select__item ' + (active ? 'active' : '') + '"\
             data-mode="' + opt.mode + '" data-asc="' + opt.asc + '">\
          <span class="material-symbols-outlined sort-item-icon">' + opt.icon + '</span>\
          <span class="sort-item-label">' + opt.label + '</span>\
          <span class="material-symbols-outlined sort-item-check">check</span>\
        </div>';
    }).join('');

    sortMenu.querySelectorAll('.sort-select__item').forEach(function(el) {
      el.addEventListener('click', function() {
        sortMode = el.dataset.mode;
        sortAsc = el.dataset.asc === 'true';
        sortLabel.textContent = SORT_OPTIONS.find(function(o) {
          return o.mode === sortMode && o.asc === sortAsc;
        })?.label.split(' ')[0] || 'Name';
        closeSortMenu();
        applyFilter();
      });
    });
  }

  function toggleSortMenu() {
    if (sortMenu.classList.contains('open')) closeSortMenu();
    else openSortMenu();
  }

  function openSortMenu() {
    renderSortMenu();
    sortMenu.classList.add('open');
    if (sortArrow) sortArrow.classList.add('open');
  }

  function closeSortMenu() {
    sortMenu.classList.remove('open');
    if (sortArrow) sortArrow.classList.remove('open');
  }

  sortTrigger.addEventListener('click', toggleSortMenu);
  document.addEventListener('click', function(e) {
    if (!e.target.closest('.sort-select')) closeSortMenu();
  });

  // ── Tag Filter (multi-select dropdown) ────────

  function renderTagChips() {
    var hasTags = allTags.length > 0;
    tagSelect.style.display = hasTags ? '' : 'none';
    manageTagsBtn.style.display = hasTags ? '' : 'none';

    if (!hasTags) return;

    tagSelectLabel.textContent = tagFilter || 'Tags';
    tagSelectCount.textContent = allTags.length ? '(' + allTags.length + ')' : '';

    var menuHTML = '';
    if (tagFilter) {
      menuHTML += '<div class="tag-select__item" data-tag=""><span class="tag-select__item-text">All tags</span></div>';
      menuHTML += '<div class="tag-select__divider"></div>';
    }
    allTags.forEach(function(t) {
      var active = tagFilter === t;
      menuHTML += '\
        <div class="tag-select__item' + (active ? ' active' : '') + '" data-tag="' + t + '">\
          <span class="tag-radio"></span>\
          <span class="tag-select__item-text">' + t + '</span>\
        </div>';
    });
    tagMenu.innerHTML = menuHTML;
  }

  function toggleTagMenu() {
    if (tagMenu.classList.contains('open')) closeTagMenu();
    else openTagMenu();
  }

  function openTagMenu() {
    renderTagChips();
    tagMenu.classList.add('open');
    tagTrigger.querySelector('.tag-select__arrow').classList.add('open');
  }

  function closeTagMenu() {
    tagMenu.classList.remove('open');
    tagTrigger.querySelector('.tag-select__arrow').classList.remove('open');
  }

  tagTrigger.addEventListener('click', toggleTagMenu);

  tagMenu.addEventListener('click', function(e) {
    var item = e.target.closest('.tag-select__item');
    if (!item) return;
    var t = item.dataset.tag || null;
    tagFilter = t;
    loadImages();
    closeTagMenu();
  });

  document.addEventListener('click', function(e) {
    if (!e.target.closest('.tag-select')) closeTagMenu();
  });

  // Tag chip click on cards — set filter to that tag
  grid.addEventListener('click', function(e) {
    var chip = e.target.closest('.tag-chip--card');
    if (!chip) return;
    e.stopPropagation();
    var t = chip.dataset.tag;
    tagFilter = tagFilter === t ? null : t;
    loadImages();
  });

  // ── Manage Tags ────────────────────────────────

  var _renameTagPending = null;

  function openManageTags() {
    var html = '';
    allTags.forEach(function(t) {
      html += '\
        <div class="manage-tag-row">\
          <span class="material-symbols-outlined manage-tag-row__icon">sell</span>\
          <span class="manage-tag-row__name">' + t + '</span>\
          <span class="manage-tag-row__count" id="mtCount_' + t + '">...</span>\
          <button class="md-btn md-btn--tag-rename" data-tag="' + t + '">Rename</button>\
          <button class="md-btn md-btn--danger md-btn--tag-delete" data-tag="' + t + '">Delete</button>\
        </div>';
      // Count images with this tag
      var count = allImages.filter(function(img) { return img.tag === t; }).length;
      var countEl = document.getElementById('mtCount_' + t);
      // Deferred count fill
      setTimeout(function() {
        var el = document.getElementById('mtCount_' + t);
        if (el) el.textContent = count + ' image' + (count !== 1 ? 's' : '');
      }, 10);
    });
    if (!html) html = '<div style="text-align:center;color:var(--md-outline);padding:16px;">No tags yet. Add tags to images via the lightbox.</div>';
    manageTagsList.innerHTML = html;
    manageTagsDialog.classList.add('active');

    // Fill counts
    setTimeout(function() {
      allTags.forEach(function(t) {
        var count = allImages.filter(function(img) { return img.tag === t; }).length;
        var el = document.getElementById('mtCount_' + t);
        if (el) el.textContent = count + ' image' + (count !== 1 ? 's' : '');
      });
    }, 50);
  }

  function closeManageTags() {
    manageTagsDialog.classList.remove('active');
  }

  manageTagsBtn.addEventListener('click', openManageTags);
  manageTagsClose.addEventListener('click', closeManageTags);
  manageTagsDialog.addEventListener('click', function(e) {
    if (e.target === manageTagsDialog) closeManageTags();
  });

  // Rename / Delete buttons in manage dialog
  manageTagsList.addEventListener('click', function(e) {
    var btn = e.target.closest('[data-tag]');
    if (!btn) return;
    var t = btn.dataset.tag;

    if (btn.classList.contains('md-btn--tag-rename')) {
      _renameTagPending = t;
      renameTagInput.value = t;
      renameTagHint.textContent = 'Rename tag "' + t + '" for all images in this group.';
      renameTagDialog.classList.add('active');
      setTimeout(function() { renameTagInput.focus(); renameTagInput.select(); }, 150);
    }

    if (btn.classList.contains('md-btn--tag-delete')) {
      pendingDeleteTag = t;
      confirmText.textContent = 'Delete tag "' + t + '" from all images? This cannot be undone.';
      confirmDialog.classList.add('active');
    }
  });

  // Rename dialog
  renameTagCancel.addEventListener('click', function() {
    renameTagDialog.classList.remove('active');
    _renameTagPending = null;
  });

  renameTagDialog.addEventListener('click', function(e) {
    if (e.target === renameTagDialog) {
      renameTagDialog.classList.remove('active');
      _renameTagPending = null;
    }
  });

  renameTagOk.addEventListener('click', async function() {
    if (!_renameTagPending) return;
    var newTag = renameTagInput.value.trim();
    if (!newTag) { snackbar('Please enter a tag name', 'error'); return; }
    if (newTag === _renameTagPending) {
      renameTagDialog.classList.remove('active');
      _renameTagPending = null;
      return;
    }
    try {
      const res = await fetch(
        '/api/tags/' + encodeURIComponent(_renameTagPending) + '?group=' + encodeURIComponent(currentGroup),
        { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ new_tag: newTag }) }
      );
      const data = await res.json();
      if (data.error) { snackbar(data.error, 'error'); return; }
      snackbar('Renamed "' + data.old_tag + '" to "' + data.new_tag + '" (' + data.updated + ' image(s))', 'success');
      renameTagDialog.classList.remove('active');
      _renameTagPending = null;
      // Update active filter if it was the renamed tag
      if (tagFilter === data.old_tag) tagFilter = data.new_tag;
      loadImages();
      closeManageTags();
    } catch (err) { snackbar('Rename failed: ' + err.message, 'error'); }
  });

  renameTagInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') renameTagOk.click();
    if (e.key === 'Escape') { renameTagDialog.classList.remove('active'); _renameTagPending = null; }
  });

  // ── Render Grid ───────────────────────────────

  function renderGrid() {
    grid.querySelectorAll('.md-card').forEach(function(c) { c.remove(); });

    if (images.length === 0) {
      emptyState.style.display = 'flex';
      var total = allImages.length;
      imageCount.innerHTML = total > 0 ? '<strong>0</strong> / ' + total + ' images' : '<strong>0</strong> images';
      return;
    }

    emptyState.style.display = 'none';
    var totalAll = allImages.length;
    var filtered = searchQuery ? '<strong>' + images.length + '</strong> / ' + totalAll + ' images' : '<strong>' + images.length + '</strong> images';
    imageCount.innerHTML = filtered;

    images.forEach(function(img, index) {
      var card = document.createElement('div');
      card.className = 'md-card';
      card.style.animationDelay = ((index % 24) * 40) + 'ms';

      var sizeLabel = img.width && img.height
        ? img.width + '×' + img.height + ' · ' + img.formatted_size
        : img.formatted_size;

      card.dataset.index = index;
      var tagBadge = img.tag
        ? '<span class="tag-chip tag-chip--card" data-tag="' + img.tag + '">' + img.tag + '</span>'
        : '';

      card.innerHTML = '\
        <div class="md-card__check" data-check="' + index + '">\
          <span class="material-symbols-outlined">check</span>\
        </div>\
        <img class="md-card__media" src="' + img.thumbnail_url + '"\
             alt="' + img.filename + '" loading="lazy"\
             onerror="this.src=\'' + img.url + '\'">\
        <div class="md-card__content">\
          <div class="md-card__title" title="' + img.filename + '">' + img.filename + '</div>\
          <div class="md-card__subtitle">\
            <span>' + sizeLabel + '</span>\
            <span>' + img.created_formatted + '</span>\
          </div>\
          ' + tagBadge + '\
        </div>\
        <div class="md-card__actions">\
          <button class="md-icon-btn" data-action="copy" data-index="' + index + '" title="Copy link">\
            <span class="material-symbols-outlined">link</span>\
          </button>\
          <button class="md-icon-btn md-icon-btn--danger" data-action="delete" data-index="' + index + '" title="Delete">\
            <span class="material-symbols-outlined">delete</span>\
          </button>\
        </div>';

      card.addEventListener('click', function(e) {
        if (e.target.closest('.md-card__actions')) return;
        if (isSelectMode) {
          toggleSelect(index);
        } else {
          openLightbox(index);
        }
      });

      grid.appendChild(card);
    });
  }

  // Card action buttons (copy / delete) — delegated, registered once.
  grid.addEventListener('click', function iconBtnHandler(e) {
    var btn = e.target.closest('.md-icon-btn');
    if (!btn) return;
    var action = btn.dataset.action;
    var idx = parseInt(btn.dataset.index, 10);
    if (action === 'copy' && images[idx]) copyLink(idx);
    if (action === 'delete' && images[idx]) promptDelete(idx);
  });

  // ── Upload Rename Dialog ───────────────────────

  function showUploadRenameDialog(files) {
    if (!files || files.length === 0) return;
    pendingUploadFiles = Array.from(files);

    var html = '';
    for (var i = 0; i < files.length; i++) {
      var f = files[i];
      if (!f || !f.name) continue;
      var ext = f.name.lastIndexOf('.') > 0 ? f.name.slice(f.name.lastIndexOf('.')) : '';
      var base = ext ? f.name.slice(0, f.name.lastIndexOf('.')) : f.name;
      var safeName = escapeHtml(f.name);
      html += '\
        <div class="upload-file-row">\
          <span class="material-symbols-outlined file-icon">image</span>\
          <span class="file-orig" title="' + safeName + '">' + safeName + '</span>\
          <span class="material-symbols-outlined file-arrow">arrow_forward</span>\
          <input class="dialog__input" data-idx="' + i + '" value="' + escapeHtml(base) + '"\
                 placeholder="filename" autocomplete="off" data-ext="' + escapeHtml(ext) + '">\
        </div>';
    }
    uploadFileList.innerHTML = html;
    // Reset tag field and populate suggestions from existing tags
    var uploadTagInput = $('uploadTagInput');
    if (uploadTagInput) uploadTagInput.value = '';
    var uploadTagOptions = $('uploadTagOptions');
    if (uploadTagOptions) {
      uploadTagOptions.innerHTML = allTags.map(function(t) {
        return '<option value="' + t + '"></option>';
      }).join('');
    }
    uploadRenameOk.textContent = 'Upload (' + files.length + ' file' + (files.length > 1 ? 's' : '') + ')';
    uploadRenameDialog._customNames = null;
    uploadRenameDialog.classList.add('active');
    var first = uploadFileList.querySelector('.dialog__input');
    if (first) setTimeout(function() { first.focus(); }, 150);
  }

  function closeUploadRenameDialog() {
    uploadRenameDialog.classList.remove('active');
    pendingUploadFiles = null;
  }

  uploadRenameCancel.addEventListener('click', closeUploadRenameDialog);
  uploadRenameDialog.addEventListener('click', function(e) {
    if (e.target === uploadRenameDialog) closeUploadRenameDialog();
  });

  uploadRenameOk.addEventListener('click', function() {
    var files = pendingUploadFiles;
    if (!files || files.length === 0) return;

    var customNames = [];
    uploadFileList.querySelectorAll('.dialog__input').forEach(function(inp) {
      var val = inp.value.trim();
      var ext = inp.dataset.ext || '';
      var idx = parseInt(inp.dataset.idx, 10);
      if (val) {
        customNames.push(val + ext);
      } else {
        customNames.push(files[idx]?.name || '');
      }
    });

    var tagInput = $('uploadTagInput');
    var uploadTag = tagInput ? tagInput.value.trim() : '';

    closeUploadRenameDialog();
    uploadFiles(files, customNames, uploadTag);
  });

  // ── Upload ────────────────────────────────────

  async function uploadFiles(files, customNames, tag) {
    if (!files || files.length === 0) return;

    var formData = new FormData();
    for (var fi = 0; fi < files.length; fi++) {
      formData.append('files', files[fi]);
    }
    if (customNames && customNames.length > 0) {
      formData.append('filenames', JSON.stringify(customNames));
    }
    if (tag) {
      formData.append('tag', tag);
    }

    uploadProgress.classList.add('active');
    progressFill.style.width = '0%';
    progressText.textContent = 'Uploading ' + files.length + ' file(s)…';

    try {
      const xhr = new XMLHttpRequest();
      const promise = new Promise(function(resolve, reject) {
        xhr.upload.addEventListener('progress', function(e) {
          if (e.lengthComputable) {
            progressFill.style.width = Math.round((e.loaded / e.total) * 100) + '%';
          }
        });
        xhr.addEventListener('load', function() {
          if (xhr.status >= 200 && xhr.status < 300) {
            try { resolve(JSON.parse(xhr.responseText)); }
            catch (e) { reject(new Error('Failed to parse response')); }
          } else {
            try {
              var errData = JSON.parse(xhr.responseText);
              reject(new Error(errData.error || 'HTTP ' + xhr.status));
            } catch (e) {
              reject(new Error('Upload failed (HTTP ' + xhr.status + ')'));
            }
          }
        });
        xhr.addEventListener('error', function() { reject(new Error('Network error')); });
        xhr.open('POST', '/api/upload?group=' + encodeURIComponent(currentGroup));
        xhr.send(formData);
      });

      const result = await promise;
      progressFill.style.width = '100%';
      progressText.textContent = 'Upload complete ✓';

      if (result.uploaded && result.uploaded.length > 0) {
        snackbar('Uploaded ' + result.uploaded.length + ' image(s)', 'success');
      }
      if (result.errors && result.errors.length > 0) {
        result.errors.forEach(function(e) { snackbar(e.filename + ': ' + e.error, 'error'); });
      }

      await loadImages();
      loadGroups();

    } catch (err) {
      snackbar('Upload failed: ' + err.message, 'error');
    } finally {
      setTimeout(function() {
        uploadProgress.classList.remove('active');
        progressFill.style.width = '0%';
      }, 1500);
    }
  }

  // ── Upload Events ─────────────────────────────

  fileInput.addEventListener('change', function() {
    if (fileInput.files.length > 0) {
      showUploadRenameDialog(fileInput.files);
      fileInput.value = '';
    }
  });

  uploadZone.addEventListener('dragover', function(e) {
    e.preventDefault();
    uploadZone.classList.add('dragover');
  });

  uploadZone.addEventListener('dragleave', function(e) {
    e.preventDefault();
    uploadZone.classList.remove('dragover');
  });

  uploadZone.addEventListener('drop', function(e) {
    e.preventDefault();
    uploadZone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
      showUploadRenameDialog(e.dataTransfer.files);
    }
  });

  // ── Lightbox ─────────────────────────────────

  function openLightbox(index) {
    if (index < 0 || index >= images.length) return;
    currentIndex = index;
    var img = images[index];
    lightboxImg.src = img.url;
    lbFilename.textContent = img.filename;
    var dims = img.width && img.height ? img.width + '×' + img.height + ' · ' : '';
    lbMeta.textContent = dims + img.formatted_size + ' · ' + img.created_formatted;
    lightbox.classList.add('active');
    document.body.style.overflow = 'hidden';
    updateNavButtons();
    updateLbTag();
  }

  function closeLightbox() {
    lightbox.classList.remove('active');
    document.body.style.overflow = '';
  }

  function updateNavButtons() {
    lightboxPrev.style.display = currentIndex > 0 ? '' : 'none';
    lightboxNext.style.display = currentIndex < images.length - 1 ? '' : 'none';
  }

  function navLightbox(delta) {
    var idx = currentIndex + delta;
    if (idx >= 0 && idx < images.length) {
      openLightbox(idx);
    }
  }

  lightboxClose.addEventListener('click', closeLightbox);
  lightboxPrev.addEventListener('click', function() { navLightbox(-1); });
  lightboxNext.addEventListener('click', function() { navLightbox(1); });

  document.addEventListener('keydown', function(e) {
    if (!lightbox.classList.contains('active')) return;
    if (document.querySelector('.dialog-overlay.active')) return;
    if (e.key === 'Escape') closeLightbox();
    if (e.key === 'ArrowLeft') navLightbox(-1);
    if (e.key === 'ArrowRight') navLightbox(1);
  });

  lightbox.addEventListener('click', function(e) {
    if (e.target === lightbox) closeLightbox();
  });

  lbDelete.addEventListener('click', function() {
    if (currentIndex >= 0) promptDelete(currentIndex);
  });

  // ── Lightbox Tag ──────────────────────────────

  function updateLbTag() {
    var img = images[currentIndex];
    if (!img) return;
    if (img.tag) {
      lbTag.textContent = img.tag;
      lbTag.style.display = '';
      lbTagBtn.title = 'Change tag';
    } else {
      lbTag.textContent = '';
      lbTag.style.display = 'none';
      lbTagBtn.title = 'Add tag';
    }
    lbTagEditor.style.display = 'none';
  }

  lbTagBtn.addEventListener('click', function() {
    if (currentIndex < 0) return;
    var img = images[currentIndex];
    lbTagInput.value = img.tag || '';
    lbTagEditor.style.display = '';

    // Build suggestion list from existing tags
    var html = '';
    allTags.forEach(function(t) {
      html += '<div class="tag-suggestion' + (t === img.tag ? ' active' : '') + '" data-tag="' + t + '">' + t + '</div>';
    });
    lbTagSuggestions.innerHTML = html;
    if (html) lbTagSuggestions.style.display = '';
    else lbTagSuggestions.style.display = 'none';

    setTimeout(function() { lbTagInput.focus(); lbTagInput.select(); }, 100);
  });

  lbTagInput.addEventListener('input', function() {
    var val = lbTagInput.value.trim().toLowerCase();
    var items = lbTagSuggestions.querySelectorAll('.tag-suggestion');
    items.forEach(function(el) {
      var match = !val || el.dataset.tag.toLowerCase().includes(val);
      el.style.display = match ? '' : 'none';
    });
  });

  lbTagSuggestions.addEventListener('click', function(e) {
    var el = e.target.closest('.tag-suggestion');
    if (!el) return;
    lbTagInput.value = el.dataset.tag;
    lbTagSuggestions.style.display = 'none';
    lbTagInput.focus();
  });

  lbTagSave.addEventListener('click', async function() {
    if (currentIndex < 0) return;
    var img = images[currentIndex];
    var tag = lbTagInput.value.trim();
    if (!tag) return;

    try {
      const res = await fetch(
        '/api/image/' + encodeURIComponent(img.filename) + '/tag?group=' + encodeURIComponent(currentGroup),
        { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tag: tag }) }
      );
      const data = await res.json();
      if (data.error) { snackbar('Tag failed: ' + data.error, 'error'); return; }
      snackbar('Tag set to "' + data.tag + '"', 'success');
      lbTagEditor.style.display = 'none';
      if (data.info) {
        images[currentIndex] = data.info;
        updateLbTag();
      }
      await loadImages();
    } catch (err) { snackbar('Tag failed: ' + err.message, 'error'); }
  });

  lbTagClear.addEventListener('click', async function() {
    if (currentIndex < 0) return;
    var img = images[currentIndex];
    try {
      const res = await fetch(
        '/api/image/' + encodeURIComponent(img.filename) + '/tag?group=' + encodeURIComponent(currentGroup),
        { method: 'DELETE' }
      );
      const data = await res.json();
      if (data.error) { snackbar('Clear tag failed: ' + data.error, 'error'); return; }
      snackbar('Tag removed', 'success');
      lbTagEditor.style.display = 'none';
      if (data.info) {
        images[currentIndex] = data.info;
        updateLbTag();
      }
      await loadImages();
    } catch (err) { snackbar('Clear tag failed: ' + err.message, 'error'); }
  });

  lbTagInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') lbTagSave.click();
    if (e.key === 'Escape') { lbTagEditor.style.display = 'none'; }
  });

  // Close tag editor when clicking outside
  document.addEventListener('click', function(e) {
    if (lbTagEditor.style.display !== 'none' &&
        !e.target.closest('.lightbox__tag-editor') &&
        !e.target.closest('.md-icon-btn--tag')) {
      lbTagEditor.style.display = 'none';
    }
  });

  // ── Rename ─────────────────────────────────────

  lbRename.addEventListener('click', function() {
    if (currentIndex < 0) return;
    var img = images[currentIndex];
    renameInput.value = img.filename;
    renameDialog.classList.add('active');
    setTimeout(function() {
      renameInput.focus();
      var dot = img.filename.lastIndexOf('.');
      if (dot > 0) renameInput.setSelectionRange(0, dot);
    }, 150);
  });

  renameCancel.addEventListener('click', function() {
    renameDialog.classList.remove('active');
  });

  renameDialog.addEventListener('click', function(e) {
    if (e.target === renameDialog) renameDialog.classList.remove('active');
  });

  renameOk.addEventListener('click', async function() {
    if (currentIndex < 0) return;
    var img = images[currentIndex];
    var newName = renameInput.value.trim();
    if (!newName) {
      snackbar('Please enter a filename', 'error');
      return;
    }
    if (newName === img.filename) {
      renameDialog.classList.remove('active');
      return;
    }

    renameOk.disabled = true;
    renameOk.textContent = 'Renaming…';

    try {
      const res = await fetch(
        '/api/image/' + encodeURIComponent(img.filename) + '/rename?group=' + encodeURIComponent(currentGroup),
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ new_name: newName }),
        }
      );
      const data = await res.json();
      if (data.error) {
        snackbar('Rename failed: ' + data.error, 'error');
        return;
      }
      snackbar('Renamed to ' + data.filename, 'success');
      renameDialog.classList.remove('active');
      if (data.info && currentIndex >= 0) {
        images[currentIndex] = data.info;
        lbFilename.textContent = data.info.filename;
        var dims = data.info.width && data.info.height
          ? data.info.width + '×' + data.info.height + ' · ' : '';
        lbMeta.textContent = dims + data.info.formatted_size + ' · ' + data.info.created_formatted;
        lightboxImg.src = data.info.url;
      }
      var newFilename = data.filename;
      await loadImages();
      var foundIdx = images.findIndex(function(x) { return x.filename === newFilename; });
      if (foundIdx >= 0) currentIndex = foundIdx;
      if (foundIdx >= 0 && images[foundIdx]) {
        var info = images[foundIdx];
        lbFilename.textContent = info.filename;
        lbMeta.textContent = (info.width ? info.width + '×' + info.height + ' · ' : '') + info.formatted_size + ' · ' + info.created_formatted;
        lightboxImg.src = info.url;
      }
      loadGroups();
    } catch (err) {
      snackbar('Rename failed: ' + err.message, 'error');
    } finally {
      renameOk.disabled = false;
      renameOk.textContent = 'Rename';
    }
  });

  renameInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') renameOk.click();
    if (e.key === 'Escape') renameDialog.classList.remove('active');
  });

  // ── Move to Group ──────────────────────────────

  lbMove.addEventListener('click', function() {
    if (currentIndex < 0) return;
    var img = images[currentIndex];
    moveFilenameLabel.textContent = img.filename;
    buildMoveGroupList();
    moveDialog._batchMode = false;
    moveDialog.classList.add('active');
  });

  function buildMoveGroupList() {
    fetch('/api/groups')
      .then(function(r) { return r.json(); })
      .then(function(groups) {
        moveGroupList.innerHTML = '';
        var selected = null;
        groups.forEach(function(g) {
          if (g.name === currentGroup) return;
          var item = document.createElement('div');
          item.className = 'group-radio-item';
          item.dataset.group = g.name;
          item.innerHTML = '\
            <div class="radio-dot"></div>\
            <span class="material-symbols-outlined radio-icon">folder</span>\
            <span class="radio-name">' + g.name + '</span>\
            <span class="radio-count">' + g.count + ' images</span>';
          item.addEventListener('click', function() {
            if (selected) selected.classList.remove('selected');
            item.classList.add('selected');
            selected = item;
          });
          moveGroupList.appendChild(item);
        });
        var first = moveGroupList.querySelector('.group-radio-item');
        if (first) first.classList.add('selected');
      })
      .catch(function(err) { snackbar('Failed to load groups: ' + err.message, 'error'); });
  }

  moveCancel.addEventListener('click', function() {
    moveDialog.classList.remove('active');
  });

  moveDialog.addEventListener('click', function(e) {
    if (e.target === moveDialog) moveDialog.classList.remove('active');
  });

  moveOk.addEventListener('click', async function() {
    var selected = moveGroupList.querySelector('.group-radio-item.selected');
    if (!selected) {
      snackbar('Please select a target group', 'error');
      return;
    }
    var toGroup = selected.dataset.group;

    moveOk.disabled = true;
    moveOk.textContent = 'Moving…';

    try {
      if (moveDialog._batchMode) {
        var names = [...selectedSet].map(function(i) { return images[i].filename; });
        const res = await fetch('/api/images/batch-move', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ group: currentGroup, to_group: toGroup, files: names }),
        });
        const data = await res.json();
        if (data.moved && data.moved.length > 0) {
          snackbar('Moved ' + data.moved.length + ' image(s) to "' + toGroup + '"', 'success');
        }
        if (data.errors && data.errors.length > 0) {
          data.errors.forEach(function(e) { snackbar(e.filename + ': ' + e.error, 'error'); });
        }
        moveDialog._batchMode = false;
        moveDialog.classList.remove('active');
        exitSelectMode();
        await loadImages();
        loadGroups();
      } else {
        if (currentIndex < 0) return;
        var img = images[currentIndex];
        const res = await fetch(
          '/api/image/' + encodeURIComponent(img.filename) + '/move?group=' + encodeURIComponent(currentGroup),
          {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ to_group: toGroup }),
          }
        );
        const data = await res.json();
        if (data.error) {
          snackbar('Move failed: ' + data.error, 'error');
          return;
        }
        snackbar('Moved to "' + toGroup + '"', 'success');
        moveDialog.classList.remove('active');
        closeLightbox();
        await loadImages();
        loadGroups();
      }
    } catch (err) {
      snackbar('Move failed: ' + err.message, 'error');
    } finally {
      moveOk.disabled = false;
      moveOk.textContent = 'Move';
    }
  });

  // ── Selection Mode ─────────────────────────────

  function enterSelectMode() {
    isSelectMode = true;
    selectedSet.clear();
    grid.classList.add('selection-mode');
    selectToggle.style.display = 'none';
    toolbarSelect.classList.add('active');
    updateSelectCount();
  }

  function exitSelectMode() {
    isSelectMode = false;
    selectedSet.clear();
    grid.classList.remove('selection-mode');
    selectToggle.style.display = '';
    toolbarSelect.classList.remove('active');
    grid.querySelectorAll('.md-card__check').forEach(function(el) { el.classList.remove('checked'); });
    grid.querySelectorAll('.md-card').forEach(function(el) { el.classList.remove('selected'); });
  }

  function toggleSelect(index) {
    if (selectedSet.has(index)) {
      selectedSet.delete(index);
    } else {
      selectedSet.add(index);
    }
    updateSelectUI();
  }

  function updateSelectUI() {
    grid.querySelectorAll('.md-card__check').forEach(function(el) {
      var idx = parseInt(el.dataset.check, 10);
      el.classList.toggle('checked', selectedSet.has(idx));
    });
    grid.querySelectorAll('.md-card').forEach(function(el) {
      var idx = parseInt(el.dataset.index, 10);
      el.classList.toggle('selected', selectedSet.has(idx));
    });
    updateSelectCount();
  }

  function updateSelectCount() {
    var count = selectedSet.size;
    selectCount.textContent = count + ' selected';
    batchMoveBtn.style.display = count > 0 ? '' : 'none';
    batchTagBtn.style.display = count > 0 ? '' : 'none';
    batchDeleteBtn.style.display = count > 0 ? '' : 'none';
  }

  selectToggle.addEventListener('click', enterSelectMode);
  selectCancel.addEventListener('click', exitSelectMode);

  selectAllBtn.addEventListener('click', function() {
    if (selectedSet.size === images.length) {
      selectedSet.clear();
    } else {
      images.forEach(function(_, idx) { selectedSet.add(idx); });
    }
    updateSelectUI();
  });

  batchDeleteBtn.addEventListener('click', function() {
    if (selectedSet.size === 0) return;
    var names = [...selectedSet].map(function(i) { return images[i].filename; });
    confirmText.textContent = 'Delete ' + names.length + ' selected image(s)? This cannot be undone.';
    pendingDelete = 'batch';
    confirmDialog.classList.add('active');
  });

  // ── Batch Tag ─────────────────────────────────

  batchTagBtn.addEventListener('click', function() {
    if (selectedSet.size === 0) return;
    var count = selectedSet.size;
    batchTagCount.textContent = 'Set a tag for ' + count + ' selected image(s):';
    batchTagInput.value = '';

    // Build suggestion chips from existing tags
    var html = '';
    allTags.forEach(function(t) {
      html += '<span class="tag-chip tag-suggestion-chip" data-tag="' + t + '">' + t + '</span>';
    });
    batchTagSuggestions.innerHTML = html;

    batchTagDialog.classList.add('active');
    setTimeout(function() { batchTagInput.focus(); }, 150);
  });

  batchTagCancel.addEventListener('click', function() {
    batchTagDialog.classList.remove('active');
  });

  batchTagDialog.addEventListener('click', function(e) {
    if (e.target === batchTagDialog) batchTagDialog.classList.remove('active');
  });

  // Click suggestion chip to fill input
  batchTagSuggestions.addEventListener('click', function(e) {
    var chip = e.target.closest('.tag-suggestion-chip');
    if (!chip) return;
    batchTagInput.value = chip.dataset.tag;
    batchTagInput.focus();
  });

  batchTagOk.addEventListener('click', async function() {
    var tag = batchTagInput.value.trim();
    if (!tag) { snackbar('Please enter a tag', 'error'); return; }

    var names = [...selectedSet].map(function(i) { return images[i].filename; });

    batchTagOk.disabled = true;
    batchTagOk.textContent = 'Applying…';

    try {
      const res = await fetch('/api/images/batch-tag', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ group: currentGroup, files: names, tag: tag }),
      });
      const data = await res.json();
      if (data.error) { snackbar(data.error, 'error'); return; }
      if (data.tagged && data.tagged.length > 0) {
        snackbar('Tag "' + tag + '" applied to ' + data.tagged.length + ' image(s)', 'success');
      }
      if (data.errors && data.errors.length > 0) {
        data.errors.forEach(function(e) { snackbar(e.filename + ': ' + e.error, 'error'); });
      }
      batchTagDialog.classList.remove('active');
      exitSelectMode();
      loadImages();
    } catch (err) {
      snackbar('Batch tag failed: ' + err.message, 'error');
    } finally {
      batchTagOk.disabled = false;
      batchTagOk.textContent = 'Apply Tag';
    }
  });

  batchTagInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') batchTagOk.click();
    if (e.key === 'Escape') batchTagDialog.classList.remove('active');
  });

  batchMoveBtn.addEventListener('click', function() {
    if (selectedSet.size === 0) return;
    moveFilenameLabel.textContent = selectedSet.size + ' selected image(s)';
    buildMoveGroupList();
    moveDialog._batchMode = true;
    moveDialog.classList.add('active');
  });

  // ── Copy Link ─────────────────────────────────

  function fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    ta.style.pointerEvents = 'none';
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand('copy');
      snackbar('Link copied', 'success');
    } catch (_e) {
      snackbar('Copy failed, please copy manually', 'error');
    }
    document.body.removeChild(ta);
  }

  function copyText(text, label) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function() {
        snackbar('Copied' + label, 'success');
      }).catch(function() { fallbackCopy(text); });
    } else {
      fallbackCopy(text);
    }
  }

  function copyLink(idx) {
    var img = images[idx];
    if (!img) return;
    copyText(img.url, ' URL');
  }

  document.querySelectorAll('[data-format]').forEach(function(btn) {
    btn.addEventListener('click', function() {
      if (currentIndex < 0) return;
      var img = images[currentIndex];
      var fmt = btn.dataset.format;
      var text, label;
      if (fmt === 'markdown') {
        text = '![](' + img.url + ')';
        label = ' Markdown link';
      } else if (fmt === 'html') {
        text = '<img src="' + img.url + '" alt="' + img.filename + '">';
        label = ' HTML link';
      } else {
        text = img.url;
        label = ' URL';
      }
      copyText(text, label);
    });
  });

  // ── Delete Image ──────────────────────────────

  function promptDelete(index) {
    var img = images[index];
    if (!img) return;
    pendingDelete = index;
    confirmText.textContent = 'Delete "' + img.filename + '"? This cannot be undone.';
    confirmDialog.classList.add('active');
  }

  confirmCancel.addEventListener('click', function() {
    confirmDialog.classList.remove('active');
    pendingDelete = null;
    pendingDeleteGroup = null; pendingDeleteTag = null;
  });

  confirmOk.addEventListener('click', async function() {
    if (pendingDelete === 'batch') {
      var names = [...selectedSet].map(function(i) { return images[i].filename; });
      confirmDialog.classList.remove('active');
      pendingDelete = null;
      try {
        const res = await fetch('/api/images/batch-delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ group: currentGroup, files: names }),
        });
        const data = await res.json();
        if (data.deleted && data.deleted.length > 0) {
          snackbar('Deleted ' + data.deleted.length + ' image(s)', 'success');
        }
        if (data.errors && data.errors.length > 0) {
          data.errors.forEach(function(e) { snackbar(e.filename + ': ' + e.error, 'error'); });
        }
        exitSelectMode();
        await loadImages();
        loadGroups();
      } catch (err) {
        snackbar('Batch delete failed: ' + err.message, 'error');
      }
    } else if (pendingDelete !== null) {
      var idx = pendingDelete;
      var img = images[idx];
      confirmDialog.classList.remove('active');
      pendingDelete = null;

      if (!img) return;

      try {
        const res = await fetch(
          '/api/image/' + encodeURIComponent(img.filename) + '?group=' + encodeURIComponent(currentGroup),
          { method: 'DELETE' }
        );
        const data = await res.json();
        if (data.success) {
          snackbar('Deleted', 'success');
          if (currentIndex === idx) closeLightbox();
          await loadImages();
          loadGroups();
        } else {
          snackbar('Delete failed: ' + (data.error || 'Unknown error'), 'error');
        }
      } catch (err) {
        snackbar('Delete failed: ' + err.message, 'error');
      }
    } else if (pendingDeleteGroup !== null) {
      var name = pendingDeleteGroup;
      confirmDialog.classList.remove('active');
      pendingDeleteGroup = null; pendingDeleteTag = null;
      await deleteGroup(name);
    } else if (pendingDeleteTag !== null) {
      var t = pendingDeleteTag;
      confirmDialog.classList.remove('active');
      pendingDeleteTag = null;
      try {
        const res = await fetch('/api/tags/' + encodeURIComponent(t) + '?group=' + encodeURIComponent(currentGroup), { method: 'DELETE' });
        const data = await res.json();
        if (data.error) { snackbar(data.error, 'error'); return; }
        snackbar('Tag "' + t + '" removed from ' + data.removed + ' image(s)', 'success');
        closeManageTags();
        if (tagFilter === t) tagFilter = null;
        loadImages();
      } catch (err) { snackbar('Failed: ' + err.message, 'error'); }
    }
  });

  confirmDialog.addEventListener('click', function(e) {
    if (e.target === confirmDialog) {
      confirmDialog.classList.remove('active');
      pendingDelete = null;
      pendingDeleteGroup = null; pendingDeleteTag = null;
    }
  });

  // ── Keyboard Shortcuts ────────────────────────

  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && confirmDialog.classList.contains('active')) {
      confirmDialog.classList.remove('active');
      pendingDelete = null;
      pendingDeleteGroup = null; pendingDeleteTag = null;
    }
    if (e.key === 'Escape' && createGroupDialog.classList.contains('active')) {
      closeCreateGroupDialog();
    }
  });

  // ── Settings Dialog ───────────────────────────

  async function openSettingsDialog() {
    try {
      const res = await fetch('/api/settings');
      const data = await res.json();
      settingsDataDir.value = data.data_dir || '';
      settingsTimeout.value = (data.staging_timeout / 60) || 5;
      settingsPort.value = data.port || 6951;
      _initTheme = data.theme || 'auto';
      _initDir = data.data_dir || '';
      _initTimeoutSec = data.staging_timeout || 300;
      _initPort = data.port || 6951;
      _allowedPorts = Array.isArray(data.allowed_origin_ports) ? data.allowed_origin_ports.slice() : [];
      _initAllowedPorts = _allowedPorts.slice();
      renderAllowedPorts();
      setThemeRadio(_initTheme);
    } catch (_e) {
      settingsDataDir.value = AC.dataDir || '';
      settingsTimeout.value = 5;
      settingsPort.value = 6951;
      _initTheme = _themeMode;
      _initDir = AC.dataDir || '';
      _initTimeoutSec = 300;
      _initPort = 6951;
      _allowedPorts = [];
      _initAllowedPorts = [];
      renderAllowedPorts();
      setThemeRadio(_initTheme);
    }
    settingsDialog.classList.add('active');
    setTimeout(function() { settingsDataDir.focus(); }, 150);
  }

  function closeSettingsDialog() {
    settingsDialog.classList.remove('active');
    settingsError.style.display = 'none';
  }

  // ── Allowed Cross-Origin Ports ────────────────

  function renderAllowedPorts() {
    if (_allowedPorts.length === 0) {
      allowedPortsList.innerHTML = '<span style="font-size:0.78rem;color:var(--md-outline);">None (same-origin only)</span>';
      return;
    }
    allowedPortsList.innerHTML = _allowedPorts.map(function(p) {
      return '<span class="tag-chip" data-port="' + p + '" style="display:inline-flex;align-items:center;gap:4px;">' +
        p + '<span class="material-symbols-outlined allowed-port-remove" data-port="' + p +
        '" style="font-size:1rem;cursor:pointer;">close</span></span>';
    }).join('');
  }

  function addAllowedPort() {
    var val = parseInt(allowedPortInput.value, 10);
    if (!val || val < 1 || val > 65535) {
      snackbar('Enter a port between 1 and 65535', 'error');
      return;
    }
    if (_allowedPorts.indexOf(val) === -1) {
      _allowedPorts.push(val);
      _allowedPorts.sort(function(a, b) { return a - b; });
      renderAllowedPorts();
    }
    allowedPortInput.value = '';
    allowedPortInput.focus();
  }

  allowedPortAdd.addEventListener('click', addAllowedPort);
  allowedPortInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') { e.preventDefault(); addAllowedPort(); }
  });
  allowedPortsList.addEventListener('click', function(e) {
    var btn = e.target.closest('.allowed-port-remove');
    if (!btn) return;
    var p = parseInt(btn.dataset.port, 10);
    _allowedPorts = _allowedPorts.filter(function(x) { return x !== p; });
    renderAllowedPorts();
  });

  function samePorts(a, b) {
    if (a.length !== b.length) return false;
    var sa = [...a].sort(function(x, y) { return x - y; });
    var sb = [...b].sort(function(x, y) { return x - y; });
    return sa.every(function(v, i) { return v === sb[i]; });
  }

  function setThemeRadio(value) {
    var radios = document.getElementsByName('theme');
    for (var i = 0; i < radios.length; i++) {
      radios[i].checked = radios[i].value === value;
    }
  }

  function getThemeRadio() {
    var radios = document.getElementsByName('theme');
    for (var i = 0; i < radios.length; i++) {
      if (radios[i].checked) return radios[i].value;
    }
    return 'auto';
  }

  // Theme radio: save instantly on change (no need to click Save)
  document.getElementById('themeRadioGroup').addEventListener('change', async function() {
    var theme = getThemeRadio();
    applyTheme(theme);
    localStorage.setItem('imagehosting_theme', theme);
    _initTheme = theme;
    try {
      await fetch('/api/settings/theme', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ theme: theme }),
      });
      snackbar('Theme: ' + theme, 'success');
    } catch (err) {
      snackbar('Theme save failed: ' + err.message, 'error');
    }
  });

  function showSettingsError(msg) {
    settingsError.textContent = msg;
    settingsError.style.display = 'block';
  }

  settingsBtn.addEventListener('click', openSettingsDialog);
  settingsCancel.addEventListener('click', closeSettingsDialog);

  browseBtn.addEventListener('click', async function() {
    browseBtn.disabled = true;
    browseBtn.textContent = 'Opening…';
    try {
      const res = await fetch('/api/settings/browse', { method: 'POST' });
      const data = await res.json();
      if (data.path) {
        settingsDataDir.value = data.path;
      } else if (data.error) {
        snackbar(data.error, 'info');
      }
    } catch (err) {
      snackbar('Folder picker failed: ' + err.message, 'error');
    } finally {
      browseBtn.disabled = false;
      browseBtn.innerHTML = '<span class="material-symbols-outlined md-btn__icon">folder_open</span> Browse';
    }
  });

  settingsSave.addEventListener('click', async function() {
    var dir = settingsDataDir.value.trim();
    var timeoutMin = settingsTimeout.value.trim();
    var timeoutSec = timeoutMin ? parseInt(timeoutMin, 10) * 60 : null;
    var portVal = settingsPort.value.trim();
    var newPort = portVal ? parseInt(portVal, 10) : null;

    var dirChanged = dir && dir !== _initDir;
    var timeoutChanged = timeoutSec !== null && timeoutSec !== _initTimeoutSec;
    var portChanged = newPort !== null && newPort !== _initPort;
    var allowedPortsChanged = !samePorts(_allowedPorts, _initAllowedPorts);

    if (!dirChanged && !timeoutChanged && !portChanged && !allowedPortsChanged) {
      showSettingsError('Nothing to update');
      return;
    }

    settingsError.style.display = 'none';
    settingsSave.disabled = true;
    settingsSave.textContent = 'Saving…';

    var hasError = false;

    if (dirChanged) {
      try {
        const res = await fetch('/api/settings/data-dir', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ data_dir: dir }),
        });
        const data = await res.json();
        if (data.error) {
          showSettingsError('Directory: ' + data.error);
          hasError = true;
        } else {
          snackbar(data.message || 'Directory updated', 'success');
          await loadImages();
          loadGroups();
        }
      } catch (err) {
        showSettingsError('Directory save failed: ' + err.message);
        hasError = true;
      }
    }

    if (timeoutChanged && !hasError) {
      try {
        const res = await fetch('/api/settings/staging-timeout', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ staging_timeout: timeoutSec }),
        });
        const data = await res.json();
        if (data.error) {
          showSettingsError('Timeout: ' + data.error);
          hasError = true;
        } else {
          snackbar('Timeout saved', 'success');
        }
      } catch (err) {
        showSettingsError('Timeout save failed: ' + err.message);
        hasError = true;
      }
    }

    if (portChanged && !hasError) {
      try {
        const res = await fetch('/api/settings/port', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ port: newPort }),
        });
        const data = await res.json();
        if (data.error) {
          showSettingsError('Port: ' + data.error);
          hasError = true;
        } else {
          snackbar('Port saved. Will take effect on next restart.', 'info');
        }
      } catch (err) {
        showSettingsError('Port save failed: ' + err.message);
        hasError = true;
      }
    }

    if (allowedPortsChanged && !hasError) {
      try {
        const res = await fetch('/api/settings/allowed-ports', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ allowed_origin_ports: _allowedPorts }),
        });
        const data = await res.json();
        if (data.error) {
          showSettingsError('Allowed ports: ' + data.error);
          hasError = true;
        } else {
          _initAllowedPorts = _allowedPorts.slice();
          snackbar('Allowed cross-origin ports updated', 'success');
        }
      } catch (err) {
        showSettingsError('Allowed ports save failed: ' + err.message);
        hasError = true;
      }
    }

    if (!hasError) {
      closeSettingsDialog();
    }

    settingsSave.disabled = false;
    settingsSave.textContent = 'Save';
  });

  // Keyboard shortcuts for rename / move dialogs
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && settingsDialog.classList.contains('active')) {
      closeSettingsDialog();
    }
    if (e.key === 'Escape' && renameDialog.classList.contains('active')) {
      renameDialog.classList.remove('active');
    }
    if (e.key === 'Escape' && moveDialog.classList.contains('active')) {
      moveDialog.classList.remove('active');
    }
  });

  // ── Init ──────────────────────────────────────

  loadGroups();
  loadImages();

})();
