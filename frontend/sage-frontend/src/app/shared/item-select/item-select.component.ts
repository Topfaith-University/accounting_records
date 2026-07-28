import {
  Component, Input, Output, EventEmitter, OnInit,
  HostListener, ElementRef, forwardRef
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, NG_VALUE_ACCESSOR, ControlValueAccessor } from '@angular/forms';
import { PayablesService } from '../../services/payables.service';

interface Item {
  item_id: string;
  name: string;
  cost_price?: number;
  selling_price?: number;
  expense_account_id?: string;
  revenue_account_id?: string;
}

@Component({
  selector: 'app-item-select',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './item-select.component.html',
  providers: [{
    provide: NG_VALUE_ACCESSOR,
    useExisting: forwardRef(() => ItemSelectComponent),
    multi: true,
  }],
})
export class ItemSelectComponent implements OnInit, ControlValueAccessor {
  @Input() placeholder = 'Search or create item…';
  @Input() allItems: Item[] = [];
  @Input() priceField: 'cost_price' | 'selling_price' = 'cost_price';

  @Output() itemsChanged = new EventEmitter<Item[]>();
  @Output() itemPicked = new EventEmitter<Item>();

  searchText = '';
  showDropdown = false;
  showModal = false;
  filteredItems: Item[] = [];

  newItem = { name: '', description: '', cost_price: 0, selling_price: 0, item_type: 'SERVICE' };
  creatingItem = false;
  createError = '';

  selectedItem: Item | null = null;

  private onChange: (val: string) => void = () => {};
  private onTouched: () => void = () => {};

  constructor(
    private payablesService: PayablesService,
    private elRef: ElementRef,
  ) {}

  async ngOnInit() {
    if (this.allItems.length === 0) {
      try {
        const data = await this.payablesService.getItems();
        this.allItems = data.results ?? data;
      } catch {}
    }
    this.filteredItems = [...this.allItems];
  }

  writeValue(id: string) {
    const found = this.allItems.find(i => i.item_id === id) ?? null;
    this.selectedItem = found;
    this.searchText = found ? found.name : '';
  }

  registerOnChange(fn: (val: string) => void) { this.onChange = fn; }
  registerOnTouched(fn: () => void) { this.onTouched = fn; }

  onInput() {
    this.showDropdown = true;
    const q = this.searchText.toLowerCase();
    this.filteredItems = this.allItems.filter(i => i.name.toLowerCase().includes(q));
    if (!this.filteredItems.find(i => i.name === this.searchText)) {
      this.selectedItem = null;
      this.onChange('');
    }
  }

  selectItem(item: Item) {
    this.selectedItem = item;
    this.searchText = item.name;
    this.showDropdown = false;
    this.onChange(item.item_id);
    this.onTouched();
    this.itemPicked.emit(item);
  }

  openCreateModal() {
    this.showDropdown = false;
    this.newItem = { name: this.searchText.trim(), description: '', cost_price: 0, selling_price: 0, item_type: 'SERVICE' };
    this.createError = '';
    this.showModal = true;
  }

  async createAndSelect() {
    if (!this.newItem.name) return;
    this.creatingItem = true;
    this.createError = '';
    try {
      const created: Item = await this.payablesService.createItem(this.newItem);
      this.allItems = [...this.allItems, created];
      this.filteredItems = [...this.allItems];
      this.itemsChanged.emit(this.allItems);
      this.selectItem(created);
      this.showModal = false;
    } catch (e: any) {
      this.createError = e.response?.data?.detail
        ?? (e.response?.data ? JSON.stringify(e.response.data) : 'Failed to create item.');
    } finally {
      this.creatingItem = false;
    }
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent) {
    if (!this.elRef.nativeElement.contains(event.target)) {
      this.showDropdown = false;
    }
  }
}
