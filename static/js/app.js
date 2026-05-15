// Auto-dismiss flash messages after 6s
document.addEventListener('DOMContentLoaded', function() {
  setTimeout(function(){
    document.querySelectorAll('.flash-wrap .alert').forEach(function(el){
      try{ var bsAlert = bootstrap.Alert.getOrCreateInstance(el); bsAlert.close(); }catch(e){}
    });
  }, 6000);

  // Add loading spinner to submit buttons when forms are posted
  document.addEventListener('submit', function(e){
    var form = e.target;
    if(!(form instanceof HTMLFormElement)) return;
    var btn = form.querySelector('button[type="submit"]');
    if(btn && !btn.disabled){
      btn.disabled = true;
      var spinner = document.createElement('span');
      spinner.className = 'spinner-border spinner-border-sm me-2';
      spinner.setAttribute('role', 'status');
      spinner.setAttribute('aria-hidden', 'true');
      btn.prepend(spinner);
    }
  }, {capture: true});
});
