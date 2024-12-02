
$(function () {


  $('select[name="reason"]').select2({
        theme: "bootstrap4",
        language: 'pt-pt',
         allowClear: true,
        placeholder: 'Escreve uma Descrição',


    });

    $('#start_date').datetimepicker({
        format: 'YYYY-MM-DD',
        date: moment().format("YYYY-MM-DD"),
        locale: 'pt-pt',
        minDate: moment().format("YYYY-MM-DD")
    });

    $('#end_date').datetimepicker({
        format: 'YYYY-MM-DD',
        date: moment().format("YYYY-MM-DD"),
        locale: 'pt-pt',
        minDate: moment().format("YYYY-MM-DD")
    });


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


