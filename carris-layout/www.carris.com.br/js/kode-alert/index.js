/* Kode Alerts */
/* Default */
$(document).ready(function(){
    $(".kode-alert .closed").click(function(event){
    $(this).parents(".kode-alert").fadeToggle(350);  
    return false;
  }); 
  
   }); 
  
  /* Click to close */
  $(document).ready(function(){
    $(".kode-alert-click").click(function(event){
    $(this).fadeToggle(350);  
    return false;
  }); 
  
   }); 