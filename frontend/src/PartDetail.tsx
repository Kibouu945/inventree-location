import { renderInvenTreeLocationPartDetail as renderCatalogPartDetail } from './catalog/PartDetail';
import { LocaleFrame } from './LocaleFrame';

export function renderInvenTreeLocationPartDetail(context: any) {
  return (
    <LocaleFrame locale={context?.locale}>
      {renderCatalogPartDetail(context)}
    </LocaleFrame>
  );
}
