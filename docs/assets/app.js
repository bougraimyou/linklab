
document.querySelectorAll('[data-tabs]').forEach(function (group) {
  var buttons = group.querySelectorAll('button');
  var panels = document.querySelectorAll('[data-panel="' + group.dataset.tabs + '"]');
  buttons.forEach(function (b) {
    b.addEventListener('click', function () {
      buttons.forEach(function (x) { x.classList.remove('on'); });
      panels.forEach(function (p) { p.hidden = true; });
      b.classList.add('on');
      var target = document.querySelector('[data-panel="' + group.dataset.tabs + '-' + b.dataset.target + '"]');
      if (target) { target.hidden = false; }
    });
  });
});
