" Corpo do GetEntitySet da coleção unificada, na DPC_EXT.
" O nome da coleção é livre; publique-o em SAP_CHAMADOS_ENTITY_SET no Python.
" A entidade deve ter os oito campos de cabeçalho e DADOS_JSON (STRING).
DATA lv_numero TYPE string.

DATA(lo_filtro) = io_tech_request_context->get_filter( ).
DATA(lt_filtros) = lo_filtro->get_filter_select_options( ).

IF lines( lt_filtros ) = 1.
  DATA(ls_filtro) = lt_filtros[ 1 ].
  DATA(lv_propriedade) = to_upper( ls_filtro-property ).

  IF ( lv_propriedade = 'OBJECTID' OR lv_propriedade = 'OBJECT_ID' )
     AND lines( ls_filtro-select_options ) = 1.
    DATA(ls_opcao) = ls_filtro-select_options[ 1 ].
    DATA(lv_recebido) = CONV string( ls_opcao-low ).

    IF ls_opcao-sign = 'I' AND ls_opcao-option = 'EQ'
       AND lv_recebido IS NOT INITIAL
       AND strlen( lv_recebido ) <= 10
       AND lv_recebido CO '0123456789'.
      lv_numero = lv_recebido.
    ENDIF.
  ENDIF.
ENDIF.

IF lv_numero IS INITIAL.
  RAISE EXCEPTION TYPE /iwbep/cx_mgw_busi_exception
    EXPORTING
      textid = /iwbep/cx_mgw_busi_exception=>business_error_unlimited
      message_unlimited = `Informe o número do chamado no filtro ObjectId`
      http_status_code = '400'.
ENDIF.

DATA(lt_chamados) = zcl_solman_chamados=>consultar( iv_numero = lv_numero ).
LOOP AT lt_chamados INTO DATA(ls_chamado).
  APPEND INITIAL LINE TO et_entityset ASSIGNING FIELD-SYMBOL(<chamado>).
  MOVE-CORRESPONDING ls_chamado TO <chamado>.
ENDLOOP.
