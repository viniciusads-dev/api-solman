" Corpo do método GetEntitySet de ChamadoSet na classe DPC_EXT.
DATA lv_numero     TYPE crmd_orderadm_h-object_id.
DATA lt_guids      TYPE crmt_object_guid_tab.
DATA lt_objetos    TYPE crmt_object_name_tab.
DATA lt_cabecalhos TYPE crmt_orderadm_h_wrkt.

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
      message_unlimited = `Informe o filtro ObjectId eq '4000000145' com o número do chamado`
      http_status_code = '400'.
ENDIF.

SELECT guid FROM crmd_orderadm_h
  WHERE object_id = @lv_numero
  INTO TABLE @lt_guids.

IF lt_guids IS INITIAL.
  RETURN.
ENDIF.

CONSTANTS lc_objeto_cabecalho TYPE crmt_object_name VALUE 'ORDERADM_H'.
INSERT lc_objeto_cabecalho INTO TABLE lt_objetos.
CALL FUNCTION 'CRM_ORDER_READ'
  EXPORTING
    it_header_guid       = lt_guids
    it_requested_objects = lt_objetos
  IMPORTING
    et_orderadm_h        = lt_cabecalhos
  EXCEPTIONS
    document_not_found   = 1
    no_display_authority = 2
    no_change_authority  = 2
    OTHERS               = 3.

DATA(lv_resultado) = sy-subrc.
IF lv_resultado = 1.
  RETURN.
ELSEIF lv_resultado = 2.
  RAISE EXCEPTION TYPE /iwbep/cx_mgw_busi_exception
    EXPORTING
      textid = /iwbep/cx_mgw_busi_exception=>business_error_unlimited
      message_unlimited = 'Usuário sem autorização para ler o chamado'
      http_status_code = '403'.
ELSEIF lv_resultado <> 0.
  RAISE EXCEPTION TYPE /iwbep/cx_mgw_busi_exception
    EXPORTING
      textid = /iwbep/cx_mgw_busi_exception=>business_error_unlimited
      message_unlimited = 'Falha ao ler o cabeçalho do chamado'
      http_status_code = '500'.
ENDIF.

LOOP AT lt_cabecalhos INTO DATA(ls_cabecalho) WHERE object_id = lv_numero.
  APPEND INITIAL LINE TO et_entityset ASSIGNING FIELD-SYMBOL(<chamado>).
  MOVE-CORRESPONDING ls_cabecalho TO <chamado>.
ENDLOOP.
