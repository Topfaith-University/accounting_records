import { Pipe, PipeTransform } from '@angular/core';

@Pipe({ name: 'paginate', standalone: true, pure: true })
export class PaginatePipe implements PipeTransform {
  transform(items: any[] | null | undefined, page: number, pageSize: number): any[] {
    if (!items?.length) return [];
    return items.slice((page - 1) * pageSize, page * pageSize);
  }
}
