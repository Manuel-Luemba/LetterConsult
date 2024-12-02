$(function () {
    let action = $('input[name="action"]')[0].value;
    console.log(action, "action")

    var inicio1 = document.getElementById("start_date");
    var inicio = $('input[name="start_date"]');
    var fim = document.getElementById("end_date");
    var fim = $('input[name="end_date"]');
    // $('select[name="type"]').select2({
    //     theme: "bootstrap4",
    //     language: 'pt',
    //     allowClear: true,
    //     placeholder: 'Selecione o Chefe',
    // });


    console.log(inicio.value, "from");
    $('#start_date').datetimepicker({
        useCurrent: false,
        format: 'YYYY-MM-DD',
        //date: inicio.value,
        locale: 'pt',
        showButtonPanel: true,
        showTodayButton: true,
        keepOn: true,

    });

    inicio.datetimepicker('date', inicio.val());


    $('#end_date').datetimepicker({
        useCurrent: false,
        format: 'YYYY-MM-DD',
        //date: fim.value,
        locale: 'pt',
        keepOn: false,

    });

   fim.datetimepicker('date', fim.val());


    if (action === "add") {

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

    }

// if( action === "edit"){
//
//     $('#start_date').datetimepicker({
//             format: 'YYYY-MM-DD',
//             date: moment().format("YYYY-MM-DD"),
//             locale: 'pt-pt',
//             minDate: moment().format("YYYY-MM-DD")
//         });
//
//     $('#end_date').datetimepicker({
//         format: 'YYYY-MM-DD',
//         date: moment().format("YYYY-MM-DD"),
//         locale: 'pt-pt',
//         minDate: moment().format("YYYY-MM-DD")
//     });
//
// }


    $('#type').select2({
          theme: "bootstrap4",
          language: 'pt-pt',
           allowClear: true,
          placeholder: 'Escreve uma Descrição',

      });

    // $('select[name="type"]').select2({
    //       theme: "bootstrap4",
    //       language: 'pt-pt',
    //        allowClear: true,
    //       placeholder: 'Escreve uma Descrição',
    //   });


    // search clients
    // $('select[name="type"]').select2({
    //     theme: "bootstrap4",
    //     language: 'pt-pt',
    //     allowClear: true,
    //     ajax: {
    //         delay: 250,
    //         type: 'POST',
    //         url: '/erp/type/list/',
    //         data: function (params) {
    //             var queryParameters = {
    //                 term: params.term,
    //                 action: 'searchdata'
    //             }
    //             return queryParameters;
    //         },
    //         processResults: function (data) {
    //         console.log(data)
    //         console.log(window.location.pathname)
    //             return {
    //                 results: data
    //             };
    //         },
    //     },
    //     placeholder: 'Escreve uma Descrição',
    //     minimumInputLength: 1,
    // });

});


