/* SurveyMind · navigation + language toggle */
(function(){
  var steps   = Array.prototype.slice.call(document.querySelectorAll('.step'));
  var screens = Array.prototype.slice.call(document.querySelectorAll('.screen'));
  var main    = document.getElementById('main');
  var order   = ['build','upload','overview','insight','types','stats','cross','export'];

  function setScreen(name){
    var target = document.getElementById('screen-' + name);
    if(!target) return; // upload has no screen here
    screens.forEach(function(s){ s.classList.toggle('active', s.id === 'screen-' + name); });
    var idx = order.indexOf(name);
    steps.forEach(function(st){
      var n = st.getAttribute('data-screen');
      var i = order.indexOf(n);
      st.classList.toggle('current', n === name);
      st.classList.toggle('done', i < idx);
    });
    if(main) main.scrollTop = 0;
    try{ localStorage.setItem('sm_screen', name); }catch(e){}
  }

  steps.forEach(function(st){
    st.addEventListener('click', function(){
      var n = st.getAttribute('data-screen');
      if(n === 'upload') return; // demo: upload step is complete
      setScreen(n);
    });
  });

  // "next step" buttons inside screens
  document.addEventListener('click', function(e){
    var b = e.target.closest('[data-go]');
    if(b){ setScreen(b.getAttribute('data-go')); }
  });

  // language toggle
  var langBtns = document.querySelectorAll('.lang button');
  function setLang(l){
    document.body.setAttribute('data-lang', l);
    langBtns.forEach(function(b){ b.classList.toggle('on', b.getAttribute('data-lang') === l); });
    document.documentElement.setAttribute('lang', l === 'zh' ? 'zh' : 'en');
    try{ localStorage.setItem('sm_lang', l); }catch(e){}
  }
  langBtns.forEach(function(b){ b.addEventListener('click', function(){ setLang(b.getAttribute('data-lang')); }); });

  // toggles in export screen (visual)
  document.addEventListener('click', function(e){
    var t = e.target.closest('.toggle');
    if(t){ t.classList.toggle('off'); }
  });

  // restore
  var savedLang = 'zh', savedScreen = 'overview';
  try{ savedLang = localStorage.getItem('sm_lang') || 'zh'; }catch(e){}
  try{ savedScreen = localStorage.getItem('sm_screen') || 'overview'; }catch(e){}
  setLang(savedLang);
  setScreen(document.getElementById('screen-' + savedScreen) ? savedScreen : 'overview');
})();
