$(function () {

    //alert('xxx');

  var inicio = $('input[name="date_sent"]');

    $('#date_sent').datetimepicker({
        useCurrent: false,
        format: 'YYYY-MM-DD',
        //date: inicio.value,
        locale: 'pt',
        showButtonPanel: true,
        showTodayButton: true,
        keepOn: true,

    });
 inicio.datetimepicker('date', inicio.val());
   // $('select[name="manager"]').select2({
   //       theme: "bootstrap4",
   //       language: 'pt-pt',
   //        allowClear: true,
   //       placeholder: 'Selecione o Chefe',
   //   });


//     // search clients
//    $('select[name="reason"]').select2({
//        theme: "bootstrap4",
//        language: 'pt-pt',
//        allowClear: true,
//        ajax: {
//            delay: 250,
//            type: 'POST',
//            url: '/erp/type/list/',
//            data: function (params) {
//                var queryParameters = {
//                    term: params.term,
//                    action: 'searchdata'
//                }
//                return queryParameters;
//            },
//            processResults: function (data) {
//            console.log(data)
//            console.log(window.location.pathname)
//                return {
//                    results: data
//                };
//            },
//        },
//        placeholder: 'Escreve uma Descrição',
//        minimumInputLength: 1,
//    });

});


